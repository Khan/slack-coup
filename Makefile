PROJECT="slack-coup"

serve:
	dev_appserver.py --port 8090 --admin_port 8010 app.yaml

deploy:
	gcloud preview app deploy app.yaml --promote --project $(PROJECT)

.PHONY: serve deploy
