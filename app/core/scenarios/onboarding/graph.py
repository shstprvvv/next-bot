import logging
from typing import TypedDict, Annotated, Sequence, Dict, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from app.core.ports.llm import LLMClient
from app.adapters.openai_assistants.adapter import OpenAIAssistantsAdapter
import operator
import json

logger = logging.getLogger("OnboardingGraph")
logger.setLevel(logging.INFO)

# Состояние для сбора информации о новом боте
class OnboardingState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    step: str # 'greeting', 'collect_name', 'collect_knowledge', 'creating_bot', 'done'
    bot_name: Optional[str]
    knowledge_text: Optional[str]
    created_assistant_id: Optional[str]

class OnboardingScenarioGraph:
    def __init__(self, llm: LLMClient, assistants_adapter: OpenAIAssistantsAdapter):
        self.llm = llm
        self.assistants_adapter = assistants_adapter
        self.graph = self._build_graph()
        logger.info("[Init] Граф Onboarding инициализирован.")

    def _build_graph(self):
        workflow = StateGraph(OnboardingState)

        # Узлы
        workflow.add_node("chat_agent", self.chat_agent)
        workflow.add_node("create_bot_tool", self.create_bot_tool)

        # Точка входа
        workflow.set_entry_point("chat_agent")

        # Условные переходы
        workflow.add_conditional_edges(
            "chat_agent",
            self.route_after_chat,
            {
                "continue_chat": END,
                "create_bot": "create_bot_tool"
            }
        )
        
        workflow.add_edge("create_bot_tool", END)

        return workflow.compile()

    def route_after_chat(self, state: OnboardingState):
        """Определяем, нужно ли продолжать диалог или пора создавать бота."""
        if state.get("step") == "creating_bot":
            return "create_bot"
        return "continue_chat"

    async def chat_agent(self, state: OnboardingState):
        """
        Главный агент, который общается с пользователем и вытягивает из него информацию.
        Он использует LLM для поддержания естественного диалога и извлечения данных.
        """
        logger.info(f"[Onboarding] Текущий шаг: {state.get('step')}")
        
        sys_prompt = """Ты — ИИ-архитектор. Твоя задача — помочь пользователю создать его собственного умного бота для сайта.
Ты должен вести естественный диалог и последовательно собрать 2 вещи:
1. Название компании или продукта.
2. Текст базы знаний (информация о продукте, FAQ, инструкции).

Твои текущие собранные данные:
Название: {bot_name}
База знаний: {knowledge_status}

ПРАВИЛА:
- Если ты еще не знаешь название, спроси его.
- Если знаешь название, но нет базы знаний, попроси пользователя прислать текст с информацией о продукте (FAQ, описание).
- Если пользователь прислал текст для базы знаний, похвали его и скажи: "Отлично! Я начинаю создавать вашего бота. Это займет несколько секунд..." И ОБЯЗАТЕЛЬНО добавь в конце своего ответа секретную фразу: [ACTION:CREATE_BOT]
- Общайся дружелюбно, используй эмодзи. Не задавай больше одного вопроса за раз.
"""
        
        bot_name = state.get("bot_name", "Неизвестно")
        knowledge_status = "Собрана" if state.get("knowledge_text") else "Не собрана"
        
        formatted_prompt = sys_prompt.format(bot_name=bot_name, knowledge_status=knowledge_status)
        messages = [SystemMessage(content=formatted_prompt)] + list(state["messages"])
        
        response = await self.llm.generate(messages)
        reply_text = response
        
        new_state = {"messages": [AIMessage(content=reply_text)]}
        
        # Простая эвристика для обновления стейта (в идеале тут нужен Tool Calling от LLM)
        last_user_msg = state["messages"][-1].content if state["messages"] else ""
        
        if state.get("step") == "collect_name" and bot_name == "Неизвестно":
            # Предполагаем, что пользователь ответил названием
            new_state["bot_name"] = last_user_msg
            new_state["step"] = "collect_knowledge"
            
        elif state.get("step") == "collect_knowledge" and not state.get("knowledge_text"):
            # Если сообщение длинное, считаем это базой знаний
            if len(last_user_msg) > 50:
                new_state["knowledge_text"] = last_user_msg
        
        # Если LLM решила, что пора создавать бота
        if "[ACTION:CREATE_BOT]" in reply_text:
            reply_text = reply_text.replace("[ACTION:CREATE_BOT]", "").strip()
            new_state["messages"] = [AIMessage(content=reply_text)]
            new_state["step"] = "creating_bot"
            
        return new_state

    async def create_bot_tool(self, state: OnboardingState):
        """
        Узел, который физически обращается к OpenAI Assistants API и создает бота.
        """
        logger.info("[Onboarding] Запуск процесса создания бота через OpenAI Assistants API...")
        
        bot_name = state.get("bot_name")
        if bot_name is None:
            bot_name = "My_Custom_Bot"
        else:
            bot_name = str(bot_name)
            
        knowledge_text = state.get("knowledge_text")
        if knowledge_text is None:
            knowledge_text = "Нет информации."
        else:
            knowledge_text = str(knowledge_text)
            
        # Безопасная генерация имени файла
        safe_bot_name = "bot"
        if bot_name:
            try:
                safe_bot_name = str(bot_name).replace(' ', '_')
            except Exception:
                pass
            
        # Убедимся, что knowledge_text не пустой
        if not knowledge_text or not str(knowledge_text).strip():
            knowledge_text = "Нет информации."
            
        try:
            # 1. Загружаем файл в OpenAI
            logger.info(f"Загрузка файла {safe_bot_name}_kb.txt. Текст: {str(knowledge_text)[:50]}...")
            file_id = await self.assistants_adapter.upload_file_from_text(
                text_content=str(knowledge_text),
                filename=f"{safe_bot_name}_kb.txt"
            )
            
            # 2. Генерируем системный промпт для нового бота
            instructions = f"""Ты — ИИ-ассистент для проекта '{bot_name}'. 
Твоя задача — консультировать пользователей, отвечать на их вопросы и помогать с выбором.
Отвечай вежливо и профессионально.
СТРОГО используй информацию из прикрепленных файлов (базы знаний). Если ответа там нет, скажи, что не знаешь, и предложи оставить контакты.
"""
            
            # 3. Создаем Ассистента
            assistant_id = await self.assistants_adapter.create_assistant(
                name=bot_name,
                instructions=instructions,
                file_ids=[file_id]
            )
            
            success_msg = f"""🎉 Ура! Ваш бот **{bot_name}** успешно создан и готов к работе!

Его уникальный ID: `{assistant_id}`

Чтобы установить его на сайт, используйте этот код:
```html
<script>
  var ASSISTANT_ID = '{assistant_id}';
  // ... скрипт виджета ...
</script>
```

[SWITCH_BOT:{assistant_id}]"""

            return {
                "messages": [AIMessage(content=success_msg)],
                "step": "done",
                "created_assistant_id": assistant_id
            }
            
        except Exception as e:
            logger.error(f"[Onboarding] Ошибка при создании бота: {e}", exc_info=True)
            return {
                "messages": [AIMessage(content="Произошла техническая ошибка при создании бота на серверах OpenAI. Пожалуйста, попробуйте позже.")],
                "step": "collect_knowledge" # Возвращаемся на шаг назад
            }

    async def execute(self, question: str, history: list = None, state_dict: dict = None) -> dict:
        """Главный метод для вызова из API"""
        logger.info(f"[Onboarding] Запуск графа. Вопрос: '{question}'")
        
        messages = []
        if history:
            for h in history:
                if h.startswith("Клиент: "):
                    messages.append(HumanMessage(content=h.replace("Клиент: ", "")))
                elif h.startswith("Бот: "):
                    messages.append(AIMessage(content=h.replace("Бот: ", "")))
                    
        messages.append(HumanMessage(content=question))
        
        # Восстанавливаем стейт из сессии
        initial_state = {
            "messages": messages,
            "step": state_dict.get("step", "collect_name") if state_dict else "collect_name",
            "bot_name": state_dict.get("bot_name") if state_dict else None,
            "knowledge_text": state_dict.get("knowledge_text") if state_dict else None,
            "created_assistant_id": state_dict.get("created_assistant_id") if state_dict else None
        }
        
        try:
            final_state = await self.graph.ainvoke(initial_state)
            
            result_text = final_state["messages"][-1].content
            
            # Возвращаем не только текст, но и обновленный стейт, чтобы сохранить его в Redis
            return {
                "reply": result_text,
                "state": {
                    "step": final_state.get("step"),
                    "bot_name": final_state.get("bot_name"),
                    "knowledge_text": final_state.get("knowledge_text"),
                    "created_assistant_id": final_state.get("created_assistant_id")
                }
            }
        except Exception as e:
            logger.error(f"[Onboarding] Критическая ошибка: {e}", exc_info=True)
            raise e