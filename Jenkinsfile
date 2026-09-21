pipeline {
    agent any

    environment {
        DOCKER_IMAGE = "ecommerce-django"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build Docker image') {
            steps {
                script {
                    // Build the image using the DOCKER_USERNAME environment variable
                    // (Assuming DOCKER_USERNAME is configured globally or injected)
                    sh 'docker build -t ${DOCKER_USERNAME}/${DOCKER_IMAGE}:latest .'
                }
            }
        }

        stage('Push/Test') {
            steps {
                script {
                    // Use credentials binding to securely inject Docker Hub credentials
                    // Adjust credentialsId 'dockerhub' based on your Jenkins setup
                    withCredentials([usernamePassword(credentialsId: 'dockerhub', passwordVariable: 'DOCKER_PASSWORD', usernameVariable: 'DOCKER_USERNAME')]) {
                        sh 'echo $DOCKER_PASSWORD | docker login -u $DOCKER_USERNAME --password-stdin'
                        sh 'docker push ${DOCKER_USERNAME}/${DOCKER_IMAGE}:latest'
                    }
                }
            }
        }
    }
    
    post {
        always {
            sh 'docker logout'
        }
    }
}
