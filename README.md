# LEO BOT: the AI for Chatbot, Marketing Automation and Personalization Engine

- For chatbot demo, please go to https://leobot.leocdp.com
- The LEO BOT works an AI chatbot with the backend using Google Generative AI (PaLM 2) and Mistral-7B
- For the GEMINI_API_KEY, please check more details at https://developers.generativeai.google/guide 
- For the GOOGLE_APPLICATION_CREDENTIALS, go to https://console.cloud.google.com/apis/api/translate.googleapis.com/credentials
- Author: Trieu Nguyen at https://github.com/trieu
- Follow my YouTube channel for more knowledge: https://www.youtube.com/@bigdatavn

## In Ubuntu server, follow this checklist to run LEO BOT

1. Need Python 3.10, run following commands
```
sudo apt install python-is-python3
curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.10
sudo apt-get install python3.10-venv
pip install virtualenv
python -m venv env
source env/bin/activate
pip install -r requirements.txt
```
2. You need to refresh the session of login shell after install python-is-python3
3. Need to create a file .env to store environment variables
4. In the file .env, set value like this example
```
LEOBOT_DEV_MODE=true
HOSTNAME=leobot.example.com

GOOGLE_APPLICATION_CREDENTIALS=
GEMINI_API_KEY=

REDIS_USER_SESSION_HOST=127.0.0.1
REDIS_USER_SESSION_PORT=6480
```
5. Set correct DIR_PATH in start_app.sh, an example like this
```
DIR_PATH="/build/leo-bot/"
```
6. Run ./start_app.sh for PRODUCTION or ./start_dev.sh for DEVELOPMENT
7. The LEO BOT is started at the host 0.0.0.0 with port 8888
8. For demo and local test, need Redis Server. Open redis-cli, run: hset demo userlogin demo
9. Go to the HOSTNAME to test your chatbot. 