import logging
from typing import TypedDict, Annotated, Sequence, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from app.core.ports.llm import LLMClient
from app.core.ports.retriever import KnowledgeRetriever
import operator

# Настройка логгера для этого модуля
logger = logging.getLogger("UniversalGraph")
logger.setLevel(logging.INFO)

# 1. Определяем состояние графа (память)
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    intent: str # 'sales', 'support', или 'unknown'
    context: str # Найденная информация из базы знаний

# 2. Создаем универсальный класс-сценарий
class UniversalScenarioGraph:
    def __init__(self, llm: LLMClient, retriever: KnowledgeRetriever, bot_config: Dict[str, Any]):
        self.llm = llm
        self.retriever = retriever
        self.bot_config = bot_config
        self.prompts = bot_config.get("prompts", {})
        self.graph = self._build_graph()
        logger.info(f"[Init] Универсальный граф для бота '{self.bot_config.get('name')}' инициализирован.")

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Добавляем узлы
        workflow.add_node("router", self.route_intent)
        workflow.add_node("retrieve_context", self.retrieve_knowledge)
        workflow.add_node("sales_agent", self.sales_response)
        workflow.add_node("support_agent", self.support_response)

        # Определяем стартовую точку
        workflow.set_entry_point("router")

        # Добавляем условные переходы
        workflow.add_conditional_edges(
            "router",
            lambda state: state["intent"],
            {
                "sales": "retrieve_context",
                "support": "retrieve_context",
                "unknown": "retrieve_context" # По умолчанию идем искать инфу
            }
        )

        # После поиска контекста решаем, какому агенту отдать
        workflow.add_conditional_edges(
            "retrieve_context",
            lambda state: state["intent"],
            {
                "sales": "sales_agent",
                "support": "support_agent",
                "unknown": "support_agent" # По умолчанию отдаем в поддержку
            }
        )

        # Завершаем граф после ответа
        workflow.add_edge("sales_agent", END)
        workflow.add_edge("support_agent", END)

        return workflow.compile()

    async def route_intent(self, state: AgentState):
        """Определяет, чего хочет пользователь: купить или решить проблему."""
        last_message = state["messages"][-1].content
        logger.info(f"[Router] Анализирую сообщение: '{last_message}'")
        
        prompt_template = self.prompts.get("router", "Ты маршрутизатор. Верни 'unknown'. Сообщение: {last_message}")
        prompt = prompt_template.format(last_message=last_message)
        
        try:
            response = await self.llm.generate(prompt)
            intent = response.strip().lower()
            
            if "sales" in intent: intent = "sales"
            elif "support" in intent: intent = "support"
            else: intent = "unknown"
            
            logger.info(f"[Router] Определен интент: {intent}")
            return {"intent": intent}
        except Exception as e:
            logger.error(f"[Router] Ошибка при определении интента: {e}")
            return {"intent": "unknown"}

    def retrieve_knowledge(self, state: AgentState):
        """Ищет информацию в Qdrant."""
        last_message = state["messages"][-1].content
        logger.info(f"[Retriever] Ищу информацию в Qdrant по запросу: '{last_message}'")
        
        try:
            chunks = self.retriever.retrieve(query=last_message)
            
            if not chunks:
                logger.warning("[Retriever] Ничего не найдено в базе знаний.")
                context = "В базе знаний нет информации по этому вопросу."
            else:
                context = "\n\n".join([c.content for c in chunks])
                logger.info(f"[Retriever] Успешно найдено {len(chunks)} фрагментов контекста.")
                
            return {"context": context}
        except Exception as e:
            logger.error(f"[Retriever] Ошибка при поиске в Qdrant: {e}")
            return {"context": "Ошибка доступа к базе знаний."}

    async def sales_response(self, state: AgentState):
        """Агент по продажам."""
        logger.info("[SalesAgent] Генерация ответа агентом по продажам...")
        context = state["context"]
        
        sys_prompt_template = self.prompts.get("sales", "Ты продавец. Отвечай вежливо.\n\nИнформация:\n{context}")
        sys_prompt = sys_prompt_template.format(context=context)

        messages = [SystemMessage(content=sys_prompt)]
        for msg in state["messages"]:
            messages.append(msg)
            
        try:
            response = await self.llm.generate(messages)
            logger.info("[SalesAgent] Ответ успешно сгенерирован.")
            return {"messages": [AIMessage(content=response)]}
        except Exception as e:
            logger.error(f"[SalesAgent] Ошибка генерации ответа: {e}")
            return {"messages": [AIMessage(content="Извините, произошла техническая ошибка при формировании ответа.")]}

    async def support_response(self, state: AgentState):
        """Агент технической поддержки."""
        logger.info("[SupportAgent] Генерация ответа агентом техподдержки...")
        context = state["context"]
        
        sys_prompt_template = self.prompts.get("support", "Ты техподдержка. Помоги клиенту.\n\nИнформация:\n{context}")
        sys_prompt = sys_prompt_template.format(context=context)

        messages = [SystemMessage(content=sys_prompt)]
        for msg in state["messages"]:
            messages.append(msg)
            
        try:
            response = await self.llm.generate(messages)
            logger.info("[SupportAgent] Ответ успешно сгенерирован.")
            return {"messages": [AIMessage(content=response)]}
        except Exception as e:
            logger.error(f"[SupportAgent] Ошибка генерации ответа: {e}")
            return {"messages": [AIMessage(content="Извините, произошла техническая ошибка при формировании ответа.")]}

    async def execute(self, question: str, history: list = None, session_id: str = "default") -> str:
        """Главный метод для вызова из API"""
        logger.info(f"[Execute] Запуск графа. Вопрос: '{question}'. Длина истории: {len(history) if history else 0}")
        
        messages = []
        if history:
            for h in history:
                if h.startswith("Клиент: "):
                    messages.append(HumanMessage(content=h.replace("Клиент: ", "")))
                elif h.startswith("Бот: "):
                    messages.append(AIMessage(content=h.replace("Бот: ", "")))
                    
        messages.append(HumanMessage(content=question))
        
        try:
            initial_state = {"messages": messages, "intent": "", "context": ""}
            # Убираем config с Langfuse из вызова графа, так как он вызывает ошибку
            final_state = await self.graph.ainvoke(initial_state)
            
            result = final_state["messages"][-1].content
            logger.info("[Execute] Граф успешно завершил работу.")
            return result
        except Exception as e:
            logger.error(f"[Execute] Критическая ошибка при выполнении графа: {e}", exc_info=True)
            raise e
