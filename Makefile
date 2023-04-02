BASE_DIR = $(CURDIR)

MANAGE = python $(BASE_DIR)/src/manage.py
VENV = . $(BASE_DIR)/.venv/bin/activate; cd src;

SSH = ssh meteo@skymeteo.net
SERVER_PATH = /home/www/meteo/meteo

FMT = printf "\033[34m%-20s\033[0m %s\n"
RGX = /^[0-9a-zA-Z_-]+:.*?\#/

help :: # Show this message
	@awk '{FS=": #"} $(RGX) {$(FMT),$$1,$$2}' $(MAKEFILE_LIST)

clean: # Clean project
	find . -name "*.pyc" -delete
	find . -name "*.orig" -delete

pip: # Install python dependencies
	$(VENV) pip install -r $(BASE_DIR)/requirements.txt \
	--upgrade -q --no-python-version-warning

static: # Django: collectstatic
	$(VENV) $(MANAGE) collectstatic --noinput

migrate: # Django: migrate
	$(VENV) $(MANAGE) migrate --noinput

test: # Django: test
	$(VENV) $(MANAGE) test --noinput

runserver: # Django: runserver
	$(VENV) $(MANAGE) runserver 127.0.0.1:8210

touch_reload: # Reload instance
	cd $(BASE_DIR) && touch reload

update: # Run multiple targets
	pip migrate static touch_reload

deploy: # Deploy via ssh
	$(SSH) "cd $(SERVER_PATH) && git reset --hard HEAD"
	@echo ""
	$(SSH) "cd $(SERVER_PATH) && git pull -f --quiet"
	@echo ""
	$(SSH) "cd $(SERVER_PATH) && make update"
