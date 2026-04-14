import logging
from typing import TypedDict, Annotated, Sequence, Dict, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END
from app.core.ports.llm import LLMClient
import operator
import json

from app.core.scenarios.admin.tools import ADMIN_TOOLS

logger = logging.getLogger("AdminBotGraph")
logger.setLevel(logging.INFO)

class AdminState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    client_id: str
    session_id: str
    products: list

class AdminBotGraph:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.tools = ADMIN_TOOLS
        # Биндим инструменты к LLM
        self.llm_with_tools = self.llm.client.bind_tools(self.tools)
        self.graph = self._build_graph()
        logger.info("[Init] Граф Admin Bot инициализирован.")

    def _build_graph(self):
        workflow = StateGraph(AdminState)

        # Узлы
        workflow.add_node("agent", self.call_model)
        workflow.add_node("tools", self.call_tools)

        # Точка входа
        workflow.set_entry_point("agent")

        # Условные переходы
        workflow.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "continue": "tools",
                "end": END
            }
        )
        
        workflow.add_edge("tools", "agent")

        return workflow.compile()

    def should_continue(self, state: AdminState):
        """Определяем, нужно ли вызывать Tool или мы закончили генерацию ответа."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # Если LLM решила вызвать инструмент
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"
            
        return "end"

    async def call_model(self, state: AdminState):
        """Вызов LLM с привязанными инструментами."""
        logger.info(f"[AdminBot] Вызов LLM. client_id: {state['client_id']}")
        
        sys_prompt = f"""Ты — AI-Менеджер платформы NextBot. Твоя задача — помогать клиентам автоматизировать работу с маркетплейсами и мессенджерами.
Ты общаешься с клиентом, чей ID: {state['client_id']}.

ТВОЯ ЗОНА ОТВЕТСТВЕННОСТИ (ТЕКУЩИЕ ВОЗМОЖНОСТИ):
На данный момент платформа поддерживает ТОЛЬКО:
1. Wildberries (ответы на вопросы и отзывы).
2. Ozon (ответы на вопросы и отзывы).
3. Telegram (ответы в чатах).
Если клиент спрашивает про другие площадки (Авито, Яндекс.Маркет, WhatsApp и т.д.), вежливо сообщи, что они находятся в разработке.

ТВОИ ИНСТРУМЕНТЫ (TOOLS):
1. Проверка статуса интеграций (Wildberries, Ozon).
2. Создание новых ботов для клиентов (инструмент create_sub_bot_tool).
3. Получение статистики работы ботов (инструмент get_client_stats_tool).
4. Ответы на вопросы о том, как работает платформа (инструмент search_platform_faq_tool).
5. Управление каталогом товаров (инструменты add_product_tool, delete_product_tool, update_product_tool, list_products_tool).
6. **ОНБОРДИНГ нового клиента** (инструмент onboard_new_client_tool) — создаёт полноценного бота с базой знаний.

======= СЦЕНАРИЙ ОНБОРДИНГА НОВОГО КЛИЕНТА =======

Если клиент говорит "хочу создать бота", "настрой мне бота", "я новый клиент", "подключи мне автоответы" или нечто подобное, запусти ПОШАГОВЫЙ сбор информации.

Ты ОБЯЗАН собрать данные ПОСЛЕДОВАТЕЛЬНО, задавая по 1-2 вопроса за раз. НЕ СПРАШИВАЙ всё сразу!

Порядок сбора:

**Шаг 1 — Бренд:** "Как называется ваш бренд или компания?"

**Шаг 2 — Товары:** "Какие товары вы продаёте? Опишите категорию (например, 'умные часы', 'детская одежда')."

**Шаг 3 — Описание товаров:** "Расскажите подробнее о ваших товарах: какие модели есть, их характеристики, цены, что входит в комплект. Чем подробнее — тем точнее будет отвечать бот."

**Шаг 4 — FAQ:** "Какие вопросы чаще всего задают ваши покупатели? Напишите их в формате:
В: вопрос
О: ответ
(можно несколько пар)"

**Шаг 5 — Ссылки:** "Есть ли у вас ссылки на маркетплейсы (Wildberries, Ozon) и сайт?"

**Шаг 6 — Гарантия и возврат:** "Какие условия гарантии и возврата у ваших товаров?"

**Шаг 7 — Доп. информация:** "Есть ли ещё что-то, что бот должен знать? Например, информация о приложении, доставке, акциях. Если нет — напишите 'нет'."

**Шаг 8 — Подтверждение:** Перед вызовом инструмента покажи клиенту краткую сводку собранных данных и спроси: "Всё верно? Создаю бота?"

**Шаг 9 — Создание:** Только после подтверждения вызови `onboard_new_client_tool` со всеми собранными данными. После успеха поздравь клиента!

ВАЖНО:
- Не пропускай шаги! Каждый шаг даёт боту знания для точных ответов.
- Если клиент дал мало информации на шаге, мягко попроси дополнить.
- Если клиент прислал большой текст (целый FAQ или описание) — отлично, используй его целиком.
- Клиент может прислать данные в свободной форме — ты умный, структурируй их сам.

======= КОНЕЦ СЦЕНАРИЯ ОНБОРДИНГА =======

ПРАВИЛА:
- ПРАВИЛО №1: НИКОГДА не придумывай данные! Если клиент спрашивает "что у меня подключено?", "работает ли бот?" или "какая у меня статистика?", ты ОБЯЗАН вызвать соответствующий инструмент.
- ПРАВИЛО №2: Если клиент просит "создай бота для Озон" или "хочу подключить бота к ВБ", ты ДОЛЖЕН спросить у него: 1) Имя бота, 2) Текст базы знаний (FAQ/описание магазина). Только после получения этих данных вызывай инструмент создания бота.
- ПРАВИЛО №3: Если клиент просит "добавь товар", "удали товар", "измени цену" или "покажи мои товары", используй инструменты управления каталогом.
  - Перед удалением или изменением ОБЯЗАТЕЛЬНО уточни артикул товара.
  - При добавлении собери название и цену. Если клиент не указал артикул, передай пустую строку в параметр article, система сгенерирует его автоматически.
  - Если клиент спрашивает "какие товары есть в базе?", вызови list_products_tool.
- ПРАВИЛО №4: Если клиент спрашивает "как получить API ключ?", "как настроить Telegram?" или "как бот понимает негатив?", используй инструмент search_platform_faq_tool для поиска ответа в документации.
- Если ты вызываешь инструмент, дождись его результата и только потом отвечай клиенту.
- Если инструмент вернул успешный результат создания бота (assistant_id), поздравь клиента и передай ему этот ID.

СТИЛЬ ОБЩЕНИЯ:
- Будь кратким, профессиональным и дружелюбным.
- Используй списки для перечисления информации.
- Используй 1-2 уместных эмодзи на сообщение.
- Предлагай следующие шаги (проактивность). Например, если ты проверил статус и увидел ошибку ключа Ozon, предложи инструкцию, как его обновить.
"""
        
        messages = [SystemMessage(content=sys_prompt)] + list(state["messages"])
        
        # Вызываем LLM с инструментами
        response = await self.llm_with_tools.ainvoke(messages)
        
        return {"messages": [response]}

    async def call_tools(self, state: AdminState):
        """Выполнение инструментов, запрошенных LLM."""
        logger.info("[AdminBot] Выполнение инструментов...")
        messages = state["messages"]
        last_message = messages[-1]
        
        tool_messages = []
        products = state.get("products", [])
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            logger.info(f"[AdminBot] Вызов инструмента: {tool_name} с аргументами {tool_args}")
            
            tool_instance = next((t for t in self.tools if t.name == tool_name), None)
            
            if tool_instance:
                try:
                    if "client_id" in tool_instance.args_schema.schema()["properties"]:
                        tool_args["client_id"] = state["client_id"]
                        
                    result = await tool_instance.ainvoke(tool_args)
                    tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
                    
                    if tool_name == "list_products_tool":
                        try:
                            data = json.loads(result)
                            if data.get("products"):
                                products = data["products"]
                        except (json.JSONDecodeError, TypeError):
                            pass
                    elif tool_name == "add_product_tool":
                        try:
                            data = json.loads(result)
                            if data.get("status") == "success":
                                products.append({"_action": "added"})
                        except (json.JSONDecodeError, TypeError):
                            pass

                except Exception as e:
                    logger.error(f"[AdminBot] Ошибка при выполнении инструмента {tool_name}: {e}")
                    tool_messages.append(ToolMessage(content=f"Ошибка: {str(e)}", tool_call_id=tool_call["id"]))
            else:
                tool_messages.append(ToolMessage(content=f"Инструмент {tool_name} не найден", tool_call_id=tool_call["id"]))
                
        return {"messages": tool_messages, "products": products}

    async def execute(self, question: str, client_id: str, history: list = None, session_id: str = "default") -> dict:
        """Главный метод для вызова из API. Возвращает dict с text и products."""
        logger.info(f"[AdminBot] Запуск графа. Вопрос: '{question}'")
        
        messages = []
        if history:
            for h in history:
                if h.startswith("Клиент: "):
                    messages.append(HumanMessage(content=h.replace("Клиент: ", "")))
                elif h.startswith("Бот: "):
                    messages.append(AIMessage(content=h.replace("Бот: ", "")))
                    
        messages.append(HumanMessage(content=question))
        
        initial_state = {
            "messages": messages,
            "client_id": client_id,
            "session_id": session_id,
            "products": []
        }
        
        try:
            final_state = await self.graph.ainvoke(initial_state)
            
            result_msg = final_state["messages"][-1]
            return {
                "text": result_msg.content,
                "products": final_state.get("products", [])
            }
        except Exception as e:
            logger.error(f"[AdminBot] Критическая ошибка: {e}", exc_info=True)
            raise e
