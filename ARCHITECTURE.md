# Архитектурный манифест AI Support Bot
`Версия 1.2`

Это манифест для LLM-based приложения автоответов техподдержки. Он фиксирует структуру проекта, направление зависимостей и правила размещения кода/промптов/базы знаний, чтобы изменения были быстрыми и предсказуемыми.

---

## Архитектурные принципы

### Что берём из Clean Architecture
- **Ports & Adapters**: изолируем внешние зависимости (LLM-провайдер, векторная БД, каналы)
- **Направление зависимостей**: core не знает про LangChain/Telethon/FAISS
- **Use Cases**: атомарные сценарии (`AnswerQuestion`, `DetectIntent`, `EscalateToOperator`)

### Что НЕ берём
- **Strict DTO**: вход и выход — текст, плодить классы бессмысленно
- **DDD/Aggregates**: нет сложного домена с инвариантами
- **Vertical Slicing по фичам**: одна главная "фича" — ответить на вопрос

---

## Структура проекта

```
next-bot/
├── app/
│   ├── core/                      # Ядро: use cases и порты
│   │   ├── ports/                 # Интерфейсы (контракты)
│   │   │   ├── __init__.py
│   │   │   ├── llm.py             # Протокол LLM-клиента
│   │   │   ├── retriever.py       # Протокол поиска по базе знаний
│   │   │   └── conversation.py    # Протокол хранения диалогов
│   │   │
│   │   ├── use_cases/             # Сценарии (бизнес-логика)
│   │   │   ├── __init__.py
│   │   │   ├── answer_question.py # Главный: вопрос → ответ
│   │   │   ├── detect_intent.py   # Классификация интента
│   │   │   └── rewrite_query.py   # Переформулировка follow-up
│   │   │
│   │   └── models/                # Доменные модели (простые dataclass)
│   │       ├── __init__.py
│   │       ├── intent.py          # Enum интентов
│   │       └── conversation.py    # Структура диалога
│   │
│   ├── adapters/                  # Реализации портов
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   └── openai_adapter.py  # Обёртка над OpenAI/LangChain
│   │   │
│   │   ├── retriever/
│   │   │   ├── __init__.py
│   │   │   └── faiss_retriever.py # FAISS + embeddings
│   │   │
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   └── buffer_memory.py   # In-memory хранение диалогов
│   │   │
│   │   ├── orchestration/         # LangChain chains, agents, tools
│   │   │   ├── __init__.py
│   │   │   ├── chains/            # LangChain chains
│   │   │   │   ├── __init__.py
│   │   │   │   ├── qa_chain.py    # ConversationalRetrievalChain
│   │   │   │   └── condense_chain.py  # Переформулировка вопроса
│   │   │   ├── agents/            # LangChain agents
│   │   │   │   ├── __init__.py
│   │   │   │   ├── support_agent.py   # ReAct/Tool-calling agent
│   │   │   │   └── stage_analyzer.py  # Классификатор стадии диалога
│   │   │   └── tools/             # Tools для агентов
│   │   │       ├── __init__.py
│   │   │       ├── knowledge_tool.py  # Поиск по базе знаний
│   │   │       ├── escalate_tool.py   # Эскалация на оператора
│   │   │       └── wb_tools.py        # Инструменты WB API
│   │   │
│   │   └── channels/              # Входящие адаптеры (каналы)
│   │       ├── __init__.py
│   │       ├── telegram/
│   │       │   ├── __init__.py
│   │       │   ├── client.py
│   │       │   └── handlers.py
│   │       └── wildberries/
│   │           ├── __init__.py
│   │           ├── api.py
│   │           └── background.py
│   │
│   ├── prompts/                   # Промпты — это тоже код
│   │   ├── __init__.py
│   │   ├── qa_prompt.py           # Основной промпт ответа
│   │   ├── intent_prompt.py       # Промпт классификации
│   │   └── rewrite_prompt.py      # Промпт переформулировки
│   │
│   ├── config.py                  # Загрузка конфигурации
│   └── logging_config.py          # Настройка логирования
│
├── knowledge/                     # База знаний (отдельно от кода)
│   ├── base.md                    # Основная база (Markdown)
│   ├── next_box.md                # (опционально) по продуктам
│   └── next_tv.md
│
├── tests/
│   ├── unit/                      # Unit-тесты
│   │   ├── test_intent_detection.py
│   │   └── test_query_rewrite.py
│   ├── integration/               # Интеграционные
│   │   └── test_full_flow.py
│   └── regression/                # Regression на реальных фейлах
│       ├── test_cases.csv         # CSV с вопросами и ожидаемыми ответами
│       └── test_regression.py
│
├── main.py                        # Composition Root (сборка зависимостей)
├── requirements.txt
├── Dockerfile
└── ARCHITECTURE.md                # Этот файл
```

---

## Описание слоёв

### `app/core/` — Ядро приложения

**Правило**: этот слой НЕ ЗНАЕТ про LangChain, FAISS, Telethon, OpenAI. Только чистый Python и абстракции.

#### `core/ports/` — Порты (интерфейсы)

Порт — это контракт. "Мне нужна штука, которая умеет X". Как именно она это делает — неважно.

```python
# core/ports/llm.py
from typing import Protocol

class LLMClient(Protocol):
    async def generate(self, prompt: str, context: str) -> str:
        """Генерирует ответ по промпту и контексту."""
        ...
```

```python
# core/ports/retriever.py
from typing import Protocol
from dataclasses import dataclass

@dataclass
class RetrievedChunk:
    content: str
    score: float
    metadata: dict

class KnowledgeRetriever(Protocol):
    def retrieve(self, query: str, k: int = 6) -> list[RetrievedChunk]:
        """Ищет релевантные куски в базе знаний."""
        ...
```

#### `core/use_cases/` — Сценарии

Use Case — атомарная единица логики. Один вопрос — один ответ. Зависит только от портов.

```python
# core/use_cases/answer_question.py
from dataclasses import dataclass
from app.core.ports.llm import LLMClient
from app.core.ports.retriever import KnowledgeRetriever

@dataclass
class AnswerQuestionUseCase:
    llm: LLMClient
    retriever: KnowledgeRetriever
    
    async def execute(self, user_id: int, question: str, history: list[str]) -> str:
        # 1. Найти релевантный контекст
        chunks = self.retriever.retrieve(question, k=6)
        context = "\n\n".join(c.content for c in chunks)
        
        # 2. Сгенерировать ответ
        prompt = self._build_prompt(question, context, history)
        answer = await self.llm.generate(prompt, context)
        
        return answer
```

**Почему это важно**: Use Case можно протестировать с моками, не поднимая OpenAI и FAISS.

---

### `app/adapters/` — Адаптеры (реализации)

Адаптер — это реализация порта. Здесь живут LangChain, FAISS, Telethon, requests.

#### `adapters/llm/` — LLM-провайдеры

```python
# adapters/llm/openai_adapter.py
from langchain_openai import ChatOpenAI
from app.core.ports.llm import LLMClient

class OpenAIAdapter:
    def __init__(self, api_key: str, base_url: str, model: str = "gpt-4o-mini"):
        self._client = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            base_url=base_url,
        )
    
    async def generate(self, prompt: str, context: str) -> str:
        response = await self._client.ainvoke(prompt)
        return response.content
```

#### `adapters/retriever/` — Векторный поиск

```python
# adapters/retriever/faiss_retriever.py
from langchain_community.vectorstores import FAISS
from app.core.ports.retriever import KnowledgeRetriever, RetrievedChunk

class FAISSRetriever:
    def __init__(self, vector_store: FAISS):
        self._store = vector_store
    
    def retrieve(self, query: str, k: int = 6) -> list[RetrievedChunk]:
        # MMR для разнообразия результатов
        docs = self._store.max_marginal_relevance_search(
            query, k=k, fetch_k=20, lambda_mult=0.7
        )
        return [
            RetrievedChunk(
                content=doc.page_content,
                score=0.0,  # FAISS MMR не возвращает score напрямую
                metadata=doc.metadata
            )
            for doc in docs
        ]
```

#### `adapters/channels/` — Входящие каналы

Telegram, Wildberries, будущий Web API — всё здесь. Канал получает сообщение, вызывает Use Case, отправляет ответ.

```python
# adapters/channels/telegram/handlers.py
from app.core.use_cases.answer_question import AnswerQuestionUseCase

def setup_handlers(client, use_case: AnswerQuestionUseCase):
    @client.on(events.NewMessage())
    async def handler(event):
        answer = await use_case.execute(
            user_id=event.sender_id,
            question=event.raw_text,
            history=[]  # TODO: подтянуть историю
        )
        await event.reply(answer)
```

---

### `app/adapters/orchestration/` — LangChain Chains, Agents, Tools

Здесь живут все LangChain-специфичные конструкции. Это **адаптеры**, потому что:
- Зависят от внешней библиотеки (LangChain)
- Могут быть заменены (chain → agent, или вообще на свою реализацию)
- Реализуют порты из `core/`

#### `orchestration/chains/` — LangChain Chains

Chains — это готовые "конвейеры" LangChain: retrieval + LLM, condense question, и т.д.

```python
# adapters/orchestration/chains/qa_chain.py
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from app.core.ports.llm import LLMClient

class QAChainAdapter:
    """Адаптер над ConversationalRetrievalChain, реализующий порт LLMClient."""
    
    def __init__(self, llm, retriever, prompt_template):
        self._memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key='answer'
        )
        self._chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=retriever,
            memory=self._memory,
            combine_docs_chain_kwargs={"prompt": prompt_template},
            return_source_documents=False,
        )
    
    async def generate(self, question: str) -> str:
        response = await self._chain.ainvoke({"question": question})
        return response.get("answer", "")
    
    def clear_memory(self):
        self._memory.clear()
```

```python
# adapters/orchestration/chains/condense_chain.py
from langchain.chains import LLMChain

class CondenseQuestionChain:
    """Переформулирует follow-up в самостоятельный вопрос."""
    
    def __init__(self, llm, prompt_template):
        self._chain = LLMChain(llm=llm, prompt=prompt_template)
    
    async def rewrite(self, question: str, chat_history: list[str]) -> str:
        history_text = "\n".join(chat_history[-6:])  # Последние 6 реплик
        result = await self._chain.ainvoke({
            "question": question,
            "chat_history": history_text
        })
        return result["text"]
```

#### `orchestration/agents/` — LangChain Agents

Agents — когда нужно динамически выбирать инструменты (tools) в зависимости от вопроса.

```python
# adapters/orchestration/agents/support_agent.py
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

class SupportAgentAdapter:
    """Agent с инструментами для сложных сценариев поддержки."""
    
    def __init__(self, llm, tools: list, prompt: ChatPromptTemplate):
        agent = create_tool_calling_agent(llm, tools, prompt)
        self._executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=5,
            handle_parsing_errors=True,
        )
    
    async def execute(self, question: str) -> str:
        result = await self._executor.ainvoke({"input": question})
        return result.get("output", "")
```

```python
# adapters/orchestration/agents/stage_analyzer.py
from langchain.chains import LLMChain

class StageAnalyzerAgent:
    """
    Определяет стадию диалога (как в SalesGPT).
    Стадии: greeting, troubleshooting, followup_not_fixed, warranty_return, angry_user, etc.
    """
    
    STAGES = {
        "greeting": "Приветствие, начало диалога",
        "troubleshooting": "Первичная диагностика проблемы", 
        "followup_not_fixed": "Пользователь говорит 'не помогло'",
        "new_topic": "Пользователь сменил тему",
        "warranty_return": "Вопрос о возврате/гарантии",
        "angry_user": "Негатив, жалоба",
        "escalate": "Запрос живого оператора",
    }
    
    def __init__(self, llm, prompt_template):
        self._chain = LLMChain(llm=llm, prompt=prompt_template)
    
    async def analyze(self, message: str, chat_history: list[str]) -> str:
        result = await self._chain.ainvoke({
            "message": message,
            "chat_history": "\n".join(chat_history[-10:]),
            "stages": "\n".join(f"- {k}: {v}" for k, v in self.STAGES.items())
        })
        return result["text"].strip().lower()
```

#### `orchestration/tools/` — Tools для агентов

Tools — это "функции", которые agent может вызывать. Каждый tool — обёртка над портом или внешним API.

```python
# adapters/orchestration/tools/knowledge_tool.py
from langchain.tools import Tool
from app.core.ports.retriever import KnowledgeRetriever

def create_knowledge_tool(retriever: KnowledgeRetriever) -> Tool:
    """Tool для поиска в базе знаний."""
    
    def search(query: str) -> str:
        chunks = retriever.retrieve(query, k=6)
        if not chunks:
            return "Информация не найдена в базе знаний."
        return "\n\n".join(c.content for c in chunks)
    
    return Tool(
        name="KnowledgeBaseSearch",
        func=search,
        description="Поиск ответа в базе знаний NEXT. Используй для любых вопросов о продукте, настройках, проблемах."
    )
```

```python
# adapters/orchestration/tools/escalate_tool.py
from langchain.tools import Tool

def create_escalate_tool(notify_callback) -> Tool:
    """Tool для эскалации на живого оператора."""
    
    def escalate(reason: str) -> str:
        notify_callback(reason)  # Отправить уведомление оператору
        return "Я передал ваш вопрос специалисту. Он скоро подключится к диалогу."
    
    return Tool(
        name="EscalateToOperator",
        func=escalate,
        description="Вызови, когда не можешь помочь или пользователь просит живого оператора."
    )
```

#### Когда использовать Chain vs Agent

| Сценарий | Что использовать |
|----------|------------------|
| Простой Q&A по базе знаний | `ConversationalRetrievalChain` |
| Нужно переформулировать follow-up | `CondenseQuestionChain` + QA Chain |
| Нужно выбирать между несколькими действиями | Agent с tools |
| Сложный multi-step сценарий (диагностика → решение → эскалация) | Agent |
| Классификация интента/стадии | Отдельный `LLMChain` (StageAnalyzer) |

---

### `app/prompts/` — Промпты как код

**Важно**: промпт — это не строка в коде. Это конфигурация поведения LLM. Храни отдельно, версионируй, тестируй.

```python
# prompts/qa_prompt.py
QA_PROMPT_TEMPLATE = """Ты — Сергей, эксперт технической поддержки бренда NEXT.

ПРАВИЛА:
- Отвечай ТОЛЬКО на основе контекста ниже
- Если ответа нет в контексте — используй фразу: "К сожалению, у меня нет готового решения..."
- Никогда не выдумывай
- Будь кратким и вежливым

КОНТЕКСТ:
{context}

ВОПРОС:
{question}

ОТВЕТ:"""

def build_qa_prompt(question: str, context: str) -> str:
    return QA_PROMPT_TEMPLATE.format(question=question, context=context)
```

---

### `knowledge/` — База знаний

Отдельная папка, не внутри `app/`. Причины:
1. Редактируют не только разработчики (контент-менеджеры, саппорт)
2. Может синхронизироваться из внешних источников
3. Легче версионировать изменения контента отдельно от кода

**Формат**: Markdown с заголовками. Каждый `###` — потенциальный чанк.

```markdown
# knowledge/base.md

## Категория: Проблемы с изображением

### Вопрос: Черный экран, синий экран, нет сигнала, мигает изображение

Ответ: ...

### Вопрос: Розовый/зеленый экран, искажение цветов

Ответ: ...
```

**Совет**: в заголовки добавляй синонимы, которые используют пользователи. Это улучшает retrieval.

---

### `tests/` — Тестирование

#### Unit-тесты
Тестируем Use Cases с моками:

```python
# tests/unit/test_answer_question.py
import pytest
from unittest.mock import AsyncMock
from app.core.use_cases.answer_question import AnswerQuestionUseCase

@pytest.mark.asyncio
async def test_returns_fallback_when_no_context():
    llm = AsyncMock()
    llm.generate.return_value = "К сожалению, у меня нет готового решения..."
    
    retriever = Mock()
    retriever.retrieve.return_value = []  # Пустой контекст
    
    use_case = AnswerQuestionUseCase(llm=llm, retriever=retriever)
    result = await use_case.execute(user_id=1, question="абракадабра", history=[])
    
    assert "нет готового решения" in result
```

#### Regression-тесты
Самые важные для AI-бота. Берёшь CSV с реальными фейлами и проверяешь, что они исправлены.

```python
# tests/regression/test_regression.py
import csv
import pytest

def load_test_cases():
    with open("tests/regression/test_cases.csv") as f:
        return list(csv.DictReader(f))

@pytest.mark.parametrize("case", load_test_cases())
@pytest.mark.asyncio
async def test_regression(case, use_case):
    question = case["question"]
    expected_contains = case["expected_contains"]  # Ключевые слова, которые должны быть в ответе
    
    result = await use_case.execute(user_id=1, question=question, history=[])
    
    assert expected_contains in result, f"Ожидали '{expected_contains}' в ответе на '{question}'"
```

---

## Composition Root (`main.py`)

Здесь собираются все зависимости. Единственное место, где знаем про конкретные реализации.

```python
# main.py
from app.adapters.llm.openai_adapter import OpenAIAdapter
from app.adapters.retriever.faiss_retriever import FAISSRetriever
from app.adapters.channels.telegram.handlers import setup_handlers
from app.core.use_cases.answer_question import AnswerQuestionUseCase

def main():
    # 1. Загрузка конфигурации
    config = load_config()
    
    # 2. Создание адаптеров
    llm = OpenAIAdapter(api_key=config["OPENAI_API_KEY"], ...)
    retriever = FAISSRetriever(...)
    
    # 3. Создание Use Cases
    answer_use_case = AnswerQuestionUseCase(llm=llm, retriever=retriever)
    
    # 4. Настройка каналов
    telegram_client = create_telegram_client(...)
    setup_handlers(telegram_client, answer_use_case)
    
    # 5. Запуск
    telegram_client.run_until_disconnected()
```

---

## Чеклист при добавлении новой функциональности

### Новый канал (например, Web API)
1. Создать `adapters/channels/web/` с роутами
2. В `main.py` добавить инициализацию и передать туда те же Use Cases
3. Не трогать `core/`

### Новый LLM-провайдер (например, Anthropic)
1. Создать `adapters/llm/anthropic_adapter.py`, реализующий `LLMClient`
2. В `main.py` заменить или добавить провайдер
3. Не трогать `core/`

### Новый Use Case (например, EscalateToOperator)
1. Создать `core/use_cases/escalate.py`
2. Определить, какие порты нужны (может, новый `NotificationPort`)
3. Реализовать адаптеры для новых портов
4. Подключить в каналах

### Новый тип данных в базе знаний
1. Добавить/изменить файлы в `knowledge/`
2. Проверить, что splitter корректно режет
3. Добавить regression-тесты

### Новый LangChain Chain
1. Создать `adapters/orchestration/chains/my_chain.py`
2. Реализовать интерфейс, совместимый с портом (например, `LLMClient`)
3. Промпт вынести в `prompts/`
4. В `main.py` собрать и передать в Use Case

### Новый LangChain Agent
1. Создать `adapters/orchestration/agents/my_agent.py`
2. Определить, какие tools нужны
3. Создать tools в `adapters/orchestration/tools/`
4. Промпт агента — в `prompts/`
5. В `main.py` собрать agent + tools и передать в Use Case

### Новый Tool для агента
1. Создать `adapters/orchestration/tools/my_tool.py`
2. Tool должен принимать порты через DI, а не создавать зависимости внутри
3. Добавить в список tools при создании агента в `main.py`

---

## Антипаттерны (чего НЕ делать)

### ❌ LangChain в Use Case
```python
# ПЛОХО: Use Case зависит от LangChain
from langchain.chains import ConversationalRetrievalChain

class AnswerQuestionUseCase:
    def __init__(self, chain: ConversationalRetrievalChain):  # Фреймворк в ядре!
        ...
```

### ❌ Промпт захардкожен в адаптере
```python
# ПЛОХО: промпт размазан по коду
class OpenAIAdapter:
    async def generate(self, question: str) -> str:
        prompt = f"Ты эксперт... {question}"  # Нельзя изменить без правки адаптера
```

### ❌ Бизнес-логика в хендлере
```python
# ПЛОХО: логика в канале
@client.on(events.NewMessage())
async def handler(event):
    if "возврат" in event.raw_text:  # Бизнес-правило в Telegram-хендлере!
        await event.reply("Оформите возврат через WB")
```

### ❌ Tool создаёт зависимости внутри себя
```python
# ПЛОХО: tool сам создаёт retriever
def create_knowledge_tool() -> Tool:
    retriever = FAISSRetriever(...)  # Зависимость создаётся внутри!
    def search(query: str) -> str:
        return retriever.retrieve(query)
    return Tool(name="Search", func=search, ...)
```

```python
# ХОРОШО: tool получает зависимости через DI
def create_knowledge_tool(retriever: KnowledgeRetriever) -> Tool:
    def search(query: str) -> str:
        chunks = retriever.retrieve(query)  # Используем переданный порт
        return "\n".join(c.content for c in chunks)
    return Tool(name="Search", func=search, ...)
```

### ❌ Agent/Chain напрямую в Use Case
```python
# ПЛОХО: Use Case зависит от конкретного agent/chain
from app.adapters.orchestration.agents.support_agent import SupportAgentAdapter

class AnswerQuestionUseCase:
    def __init__(self, agent: SupportAgentAdapter):  # Конкретный класс!
        ...
```

```python
# ХОРОШО: Use Case зависит от порта
from app.core.ports.llm import LLMClient

class AnswerQuestionUseCase:
    def __init__(self, llm: LLMClient):  # Абстракция
        ...
# А SupportAgentAdapter реализует LLMClient
```

---

## Резюме

| Слой | Что там | Зависит от |
|------|---------|------------|
| `core/ports` | Интерфейсы | Ничего |
| `core/use_cases` | Логика | Только ports |
| `core/models` | Dataclasses | Ничего |
| `adapters/llm` | LLM-провайдеры | core + langchain/openai |
| `adapters/retriever` | Векторный поиск | core + faiss/pinecone |
| `adapters/memory` | Хранение диалогов | core |
| `adapters/orchestration/chains` | LangChain chains | core + langchain |
| `adapters/orchestration/agents` | LangChain agents | core + langchain + tools |
| `adapters/orchestration/tools` | Tools для агентов | core + внешние API |
| `adapters/channels` | Telegram, WB, Web | core + telethon/requests |
| `prompts/` | Шаблоны промптов | Ничего |
| `main.py` | Сборка | Всё |

**Главное правило**: если завтра надо заменить OpenAI на Llama, поменять FAISS на Pinecone, переключиться с Chain на Agent — это изменение в `adapters/` и `main.py`, без единой правки в `core/`.
