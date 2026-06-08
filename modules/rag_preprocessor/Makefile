az_login:
	sudo az login
	sudo az acr login --name idsazwe1acrpro

docker_local_build:
	sudo docker build -t intelectia-docs-preprocessor .

docker_acr_build:
	sudo docker build -t idsazwe1acrpro.azurecr.io/intelectia-docs-preprocessor .
	sudo docker image push idsazwe1acrpro.azurecr.io/intelectia-docs-preprocessor