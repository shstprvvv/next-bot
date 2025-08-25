import os
import json
import logging
from dotenv import load_dotenv

from app.wb import api as wb

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def main():
    load_dotenv()
    print('[Check] WB key loaded:', bool(os.getenv('WB_API_KEY')))
    feedbacks = wb.get_unanswered_feedbacks(max_items=10)
    questions = wb.get_unanswered_questions(max_items=10)

    f_count = 0 if feedbacks is None else len(feedbacks)
    q_count = 0 if questions is None else len(questions)
    print('[Check] feedbacks count:', f_count)
    print('[Check] questions count:', q_count)

    if feedbacks:
        f0 = feedbacks[0]
        print('[Sample feedback] id:', f0.get('id'), 'text_len:', len((f0.get('text') or '')))
    if questions:
        q0 = questions[0]
        qtext = q0.get('text') or q0.get('questionText') or ''
        print('[Sample question] id:', q0.get('id'), 'text_len:', len(qtext))


if __name__ == '__main__':
    main()


