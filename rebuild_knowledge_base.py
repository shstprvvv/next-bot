import os
import logging
import shutil
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_community.document_loaders import UnstructuredMarkdownLoader

# Загружаем переменные окружения из .env файла
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')

KNOWLEDGE_BASE_PATH = "knowledge_base.md"
FAISS_INDEX_PATH = "faiss_index"

def rebuild_faiss_index():
    """
    Полностью перестраивает векторный индекс FAISS из файла knowledge_base.md.
    """
    if not os.path.exists(KNOWLEDGE_BASE_PATH):
        logging.error(f"Файл базы знаний не найден по пути: {KNOWLEDGE_BASE_PATH}")
        return

    logging.info("Начало перестройки индекса FAISS...")

    try:
        # 1. Загрузка и разделение документа
        logging.info(f"Загрузка данных из {KNOWLEDGE_BASE_PATH}...")
        loader = UnstructuredMarkdownLoader(KNOWLEDGE_BASE_PATH)
        docs = loader.load_and_split()
        logging.info(f"Документ успешно загружен и разделен на {len(docs)} частей.")

        # 2. Создание эмбеддингов
        logging.info("Инициализация модели эмбеддингов OpenAI...")
        embeddings = OpenAIEmbeddings()

        # 3. Удаление старого индекса, если он существует
        if os.path.exists(FAISS_INDEX_PATH):
            logging.warning(f"Удаление старой директории индекса: {FAISS_INDEX_PATH}")
            shutil.rmtree(FAISS_INDEX_PATH)

        # 4. Создание и сохранение нового индекса
        logging.info("Создание нового векторного индекса FAISS...")
        db = FAISS.from_documents(docs, embeddings)
        db.save_local(FAISS_INDEX_PATH)
        logging.info(f"Новый индекс успешно создан и сохранен в {FAISS_INDEX_PATH}.")

    except Exception as e:
        logging.error(f"Произошла ошибка во время перестройки индекса: {e}", exc_info=True)

if __name__ == "__main__":
    # Проверяем наличие ключа API OpenAI перед запуском
    if not os.getenv("OPENAI_API_KEY"):
        print("Ошибка: Переменная окружения OPENAI_API_KEY не установлена.")
        print("Пожалуйста, создайте файл .env или установите переменную перед запуском.")
    else:
        rebuild_faiss_index()
