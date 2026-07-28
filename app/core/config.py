import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
HADITH_API_KEY = os.environ["HADITH_API_KEY"]
