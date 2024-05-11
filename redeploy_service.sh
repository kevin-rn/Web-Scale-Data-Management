#! /bin/bash 

POD_NAME=$(minikube kubectl -- get pods --all-namespaces | grep -o "$1-deployment[^ ]*")

minikube kubectl -- delete pods ${POD_NAME}

minikube kubectl -- delete service/$1-service
minikube kubectl -- delete deployment.apps/$1-deployment

eval $(minikube -p minikube docker-env)

cd $1
docker build -t $1 . --no-cache

cd ../k8s

minikube kubectl -- apply -f $1-app.yaml

cd ..