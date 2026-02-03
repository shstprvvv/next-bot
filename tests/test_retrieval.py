import asyncio
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Добавляем корень проекта в sys.path, чтобы импорты работали
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.tools.knowledge_tool import create_retriever
from app.chains.factory import create_conversational_chain
from langchain_openai import ChatOpenAI

# Настройка логирования (только важные сообщения)
logging.basicConfig(level=logging.ERROR)

# Пути
TESTS_DIR = Path(__file__).resolve().parent
GOLDEN_QUESTIONS_PATH = TESTS_DIR / "golden_questions.json"

async def run_tests(full_mode: bool):
    # Загружаем переменные окружения
    load_dotenv()
    
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")

    print(f"🔹 Запуск тестов (Режим: {'FULL E2E' if full_mode else 'RETRIEVAL ONLY'})")
    print(f"🔹 Загрузка вопросов из {GOLDEN_QUESTIONS_PATH}...")

    try:
        with open(GOLDEN_QUESTIONS_PATH, "r", encoding="utf-8") as f:
            questions = json.load(f)
    except FileNotFoundError:
        print(f"❌ Файл {GOLDEN_QUESTIONS_PATH} не найден.")
        return

    print(f"🔹 Инициализация Retriever...")
    retriever = create_retriever(api_key=api_key, base_url=api_base)
    
    if not retriever:
        print("❌ Не удалось создать Retriever. Проверьте настройки или эмбеддинги.")
        return

    chain = None
    if full_mode:
        print(f"🔹 Инициализация LLM Chain...")
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            openai_api_key=api_key,
            base_url=api_base,
            temperature=0
        )
        chain = create_conversational_chain(llm, retriever)

    print("-" * 60)
    passed = 0
    failed = 0
    
    for i, question in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] В: {question}")
        
        # 1. Тест поиска (Retrieval)
        try:
            docs = retriever.invoke(question)
            if not docs:
                print(f"   ❌ RETRIEVAL FAIL: Документы не найдены.")
                failed += 1
                continue
            
            # Показываем источник лучшего совпадения
            top_doc = docs[0]
            # Пытаемся найти заголовок в метаданных или показать начало текста
            source = top_doc.metadata.get("Header 4") or top_doc.metadata.get("Header 3") or top_doc.metadata.get("Header 2") or top_doc.page_content[:50] + "..."
            print(f"   ✅ FOUND: {len(docs)} док. Топ: '{source}'")

        except Exception as e:
            print(f"   ❌ RETRIEVAL ERROR: {e}")
            failed += 1
            continue

        # 2. Тест генерации (Full Mode)
        if full_mode:
            try:
                res = await chain.ainvoke({"question": question})
                answer = res.get("answer", "").strip()
                
                # Простые проверки на "заглушку"
                fallback_phrases = [
                    "к сожалению, у меня нет готового решения",
                    "база знаний временно недоступна",
                    "произошла ошибка"
                ]
                
                if not answer or any(phrase in answer.lower() for phrase in fallback_phrases):
                     print(f"   ❌ GENERATION FAIL: Ответ похож на заглушку или пустой.")
                     print(f"      Ответ: {answer[:100]}...")
                     failed += 1
                else:
                     print(f"   ✅ GENERATED ({len(answer)} chars)")
            except Exception as e:
                print(f"   ❌ GENERATION ERROR: {e}")
                failed += 1

        if not full_mode:
            passed += 1
        elif full_mode and chain: # Если мы здесь в full mode, значит и генерация прошла (иначе бы сработал failed выше)
             passed += 1

    print("-" * 60)
    print(f"ИТОГ: Всего {len(questions)} | ✅ Успешно: {passed} | ❌ Провалено: {failed}")

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тестирование RAG бота")
    parser.add_argument("--full", action="store_true", help="Запустить полный цикл с генерацией ответов (ПЛАТНО)")
    args = parser.parse_args()

    asyncio.run(run_tests(args.full))
