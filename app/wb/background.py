import asyncio
import json
import logging
from collections import deque


async def background_wb_checker(
    wb_api_key: str,
    get_or_create_agent,
    get_unanswered_feedbacks_tool_factory,
    post_answer_tool_factory,  # Добавляем фабрику инструмента отправки
    check_interval_seconds: int,
):
    """
    Периодически проверяет и отвечает на ВОПРОСЫ Wildberries.
    (Функционал ответов на отзывы отключен для экономии)
    """
    if not wb_api_key:
        return

    logging.info("[BackgroundWB] Запуск фоновой задачи для проверки отзывов Wildberries...")
    agent_executor = get_or_create_agent(user_id=0, is_background_agent=True)

    recently_answered_ids = deque(maxlen=100)
    unanswered_tool = get_unanswered_feedbacks_tool_factory()
    post_tool = post_answer_tool_factory()  # Создаем экземпляр инструмента для отправки

    while True:
        try:
            if agent_executor.memory:
                agent_executor.memory.clear()
                logging.info("[BackgroundWB] Память фонового агента очищена перед новой проверкой.")

            logging.info("[BackgroundWB] Получение списка неотвеченных элементов...")
            items_json = unanswered_tool.func("")

            try:
                items = json.loads(items_json)
            except (json.JSONDecodeError, TypeError):
                items = []

            if not items:
                logging.info("[BackgroundWB] Новых неотвеченных элементов нет.")
            else:
                logging.info(f"[BackgroundWB] Получено {len(items)} элементов. Поиск нового для ответа...")

                # --- Новая логика: фильтруем только вопросы ---
                questions_to_answer = [item for item in items if item.get("type") == "question"]
                logging.info(f"[BackgroundWB] Найдено неотвеченных вопросов: {len(questions_to_answer)}")


                if not questions_to_answer:
                    logging.info("[BackgroundWB] Все полученные вопросы уже были недавно обработаны. Пропускаем цикл.")
                else:
                    logging.info(f"[BackgroundWB] Поиск нового вопроса для ответа...")

                    item_to_answer = None
                    for item in questions_to_answer: # Исправлена ошибка: итерируемся только по вопросам
                        if item.get("id") not in recently_answered_ids:
                            item_to_answer = item
                            break

                    if item_to_answer:
                        item_id = item_to_answer.get("id")
                        current_state = item_to_answer.get("state")  # Извлекаем текущий state
                        logging.info(f"[BackgroundWB] Найден новый вопрос для ответа. ID: {item_id}, State: {current_state}")

                        input_prompt = (
                            f"Сгенерируй ответ на следующий вопрос покупателя с Wildberries. ID вопроса: {item_id}. "
                            f"Содержимое вопроса в формате JSON: {json.dumps(item_to_answer, ensure_ascii=False)}"
                        )

                        # 1. Генерируем текстовый ответ
                        response = await agent_executor.ainvoke({"question": input_prompt}) # Ключ "input" заменен на "question"
                        answer_text = (response or {}).get("answer", "").strip() # Ответ теперь в ключе "answer"

                        if not answer_text or "не знаю" in answer_text.lower() or "нет ответа" in answer_text.lower():
                            logging.warning(f"[BackgroundWB] Сгенерирован пустой или неуверенный ответ для вопроса {item_id}. Пропускаем отправку.")
                            continue

                        logging.info(f"[BackgroundWB] Ответ для вопроса {item_id} сгенерирован. Попытка отправки...")

                        # 2. Отправляем ответ через инструмент
                        post_payload = json.dumps({
                            "feedback_id": item_id,
                            "text": answer_text,
                            "type": item_to_answer.get("type"),
                        })
                        post_result = post_tool.func(post_payload)
                        logging.info(f"[BackgroundWB] Результат отправки для {item_id}: {post_result}")

                        # 3. Проверяем результат отправки
                        if post_result and "отправлен" in post_result.lower():
                            logging.info(
                                f"[BackgroundWB] Ответ на вопрос ID {item_id} успешно отправлен. Добавляю в кэш."
                            )
                            recently_answered_ids.append(item_id)
                        else:
                            logging.warning(
                                f"[BackgroundWB] Отправка ответа на вопрос ID {item_id} могла быть неуспешной."
                            )
                    else:
                        logging.info("[BackgroundWB] Все полученные вопросы уже были недавно обработаны. Пропускаем цикл.")

        except Exception as e:
            logging.error(f"[BackgroundWB] Ошибка в фоновой задаче: {e}", exc_info=True)

        logging.info(f"[BackgroundWB] Следующая проверка через {check_interval_seconds} секунд.")
        await asyncio.sleep(check_interval_seconds)


async def background_wb_chat_responder(
    wb_api_key: str,
    get_or_create_agent,
    get_chat_events_tool_factory,
    post_chat_message_tool_factory,
    poll_interval_seconds: int,
    wb_chat_debug: bool = False,
):
    """
    Воркер опроса событий чатов WB и автоответов.
    """
    if not wb_api_key:
        return

    logging.info("[BackgroundWBChat] Запуск фоновой задачи для чатов WB...")
    agent_executor = get_or_create_agent(user_id=-1, is_background_agent=True)

    last_event_id = None
    next_token = None
    reply_sign_cache = {}
    get_events_tool = get_chat_events_tool_factory()
    send_tool = post_chat_message_tool_factory()

    while True:
        try:
            if agent_executor.memory:
                agent_executor.memory.clear()

            payload = {}
            if next_token is not None:
                payload["next"] = next_token
            elif last_event_id is not None:
                payload["last_event_id"] = last_event_id

            events_json = get_events_tool.func(json.dumps(payload))
            if wb_chat_debug:
                logging.info(f"[BackgroundWBChat] Raw events response: {events_json}")
            try:
                events = json.loads(events_json) if isinstance(events_json, str) else events_json
            except Exception:
                events = None

            if not events or not isinstance(events, dict):
                if wb_chat_debug:
                    logging.info("[BackgroundWBChat] Нет событий или неожиданный формат ответа")
                await asyncio.sleep(poll_interval_seconds)
                continue

            container = None
            if isinstance(events, dict):
                container = events.get("result") or events.get("data") or {}
            next_token = container.get("next") if isinstance(container, dict) else None
            event_list = (container or {}).get("events", []) if isinstance(container, dict) else []

            logging.info(f"[BackgroundWBChat] Получено событий: {len(event_list)}")
            for ev in event_list:
                ev_id = ev.get("id") or ev.get("eventId") or ev.get("eventID")
                if isinstance(ev_id, int):
                    last_event_id = max(last_event_id or 0, ev_id)

                ev_type = ev.get("type") or ev.get("eventType") or ev.get("event_type")
                if str(ev_type).lower() not in ("message", "msg", "user_message", "buyer_message"):
                    if wb_chat_debug:
                        logging.info(f"[BackgroundWBChat] Пропущено событие типа {ev_type}")
                    continue

                payload_message = ev.get("message") or {}
                chat_id = (
                    ev.get("chatId")
                    or ev.get("chatID")
                    or payload_message.get("chatId")
                    or payload_message.get("chatID")
                    or payload_message.get("chat_id")
                )
                text = payload_message.get("text") or ev.get("text")
                reply_sign = payload_message.get("replySign")
                sender = (ev.get("sender") or payload_message.get("sender") or "").lower()

                if chat_id and reply_sign:
                    reply_sign_cache[str(chat_id)] = reply_sign

                if sender and sender != "client":
                    if wb_chat_debug:
                        logging.info("[BackgroundWBChat] Пропуск: отправитель не клиент")
                    continue

                if not chat_id or not text:
                    if wb_chat_debug:
                        logging.info("[BackgroundWBChat] Нет chat_id или текста в событии")
                    continue

                input_prompt = (
                    f"Сгенерируй вежливый ответ на сообщение покупателя в WB чате.\n"
                    f"Сообщение: {text}"
                )
                try:
                    response = await agent_executor.ainvoke({"input": input_prompt})
                    reply = (response or {}).get("output", "")
                    if reply:
                        reply = reply.strip().replace("```", "")
                        if wb_chat_debug:
                            logging.info(f"[BackgroundWBChat] Ответ (preview): {reply[:160]}…")
                        final_reply_sign = reply_sign or reply_sign_cache.get(str(chat_id))
                        if not final_reply_sign and wb_chat_debug:
                            logging.info("[BackgroundWBChat] Нет replySign — пропускаю отправку для безопасности")
                            continue
                        send_result = send_tool.func(json.dumps({
                            "chat_id": str(chat_id),
                            "text": reply,
                            "reply_sign": final_reply_sign
                        }))
                        if isinstance(send_result, str) and send_result.startswith("Сообщение отправлено"):
                            logging.info(f"[BackgroundWBChat] Ответ отправлен в чат {chat_id}")
                        else:
                            logging.warning(f"[BackgroundWBChat] Отправка могла не пройти: {send_result}")
                except Exception as e:
                    logging.error(f"[BackgroundWBChat] Ошибка генерации/отправки ответа: {e}", exc_info=True)

        except Exception as e:
            logging.error(f"[BackgroundWBChat] Ошибка в воркере: {e}", exc_info=True)

        await asyncio.sleep(poll_interval_seconds)


