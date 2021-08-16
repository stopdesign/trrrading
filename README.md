# Trrrading

Yet Another Trading Platform


## System Requirements
* Python 3


## Deployment


### Install system requirements

#### Linux
```bash
apt update
apt install python3 virtualenv python3-virtualenv
```
#### Mac
```bash
--- TODO ---
```


### Install python requirements
```bash
cd trrrading
virtualenv -p python3 .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```


### Provide local settings
Create the `src/settings/settings_local.py` using the `settings.py` as a template.

Fill it with the correct values for your environment.


### Run the script

Inside the project directory run:
```bash
source .venv/bin/activate
python src/main.py
```
