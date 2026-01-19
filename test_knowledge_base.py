import asyncio
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from app.chains.factory import create_conversational_chain
import os

# Загружаем переменные окружения из .env
load_dotenv()

FAISS_INDEX_PATH = "faiss_index"

async def test_question(chain, question):
    """Задает вопрос и печатает ответ."""
    print("-" * 50)
    print(f">>> Вопрос: {question}")
    
    # Вызываем 체인 для получения ответа
    result = await chain.ainvoke({"question": question})
    answer = result.get("answer", "Ответ не найден.")
    
    print("\n<<< Ответ Бота:")
    print(answer)
    print("-" * 50)

async def main():
    """Основная функция для тестирования базы знаний."""
    try:
        # 1. Загружаем FAISS индекс
        print("Загрузка векторного индекса FAISS...")
        embeddings = OpenAIEmbeddings()
        # Примечание: allow_dangerous_deserialization=True необходимо для загрузки индекса,
        # созданного с помощью LangChain. Это безопасно в нашем контексте.
        db = FAISS.load_local(FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
        retriever = db.as_retriever()
        print("Индекс успешно загружен.")

        # 2. Инициализируем языковую модель
        llm = ChatOpenAI(temperature=0, model_name="gpt-4o-mini")

        # 3. Создаем разговорную цепочку, передавая и llm, и retriever
        chain = create_conversational_chain(llm, retriever)
        print("Разговорная цепочка создана. Начинаем тестирование...\n")

        # 4. Тестируем вопросы, на которые мы добавили ответы
        await test_question(chain, "Можно ли купить пульт отдельно?")
        await test_question(chain, "Какой кабель нужен для старого телевизора?")
        await test_question(chain, "Что делать, если приставка тормозит?")
        await test_question(chain, "Как вернуть товар если он бракованный?")


    except FileNotFoundError:
        print(f"ОШИБКА: Директория с индексом '{FAISS_INDEX_PATH}' не найдена.")
        print("Пожалуйста, сначала запустите 'python3 rebuild_knowledge_base.py'")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Ошибка: Переменная окружения OPENAI_API_KEY не установлена.")
    else:
        asyncio.run(main())
