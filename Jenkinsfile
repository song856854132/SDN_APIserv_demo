pipeline {
    agent any

    environment {
        IMAGE_NAME = "flask_app"
        CONTAINER_NAME = "flask_web"
        VM_USER = "chts_admin"
        VM_HOST = "10.250.28.152"
        PACKAGE_NAME = "app_package.tar.gz"
        REGISTRY = "your-registry" // e.g., docker.io/username, replace as needed
        COMPOSE_FILE = "docker-compose.yaml"
    }

    stages {
        // stage('Checkout') {
        //     steps {
        //         git url: 'https://github.com/your/repo.git', branch: 'main' // Adjust repo URL
        //     }
        // }

        stage('Build Docker') {
            steps {
                script {
                    // Build the Docker images defined in docker-compose.yaml
                    sh "docker compose -f ${COMPOSE_FILE} build"
                    // Package Python code into executable with PyInstaller
                    // sh '''
                    //     pip install pyinstaller
                    //     pyinstaller --onefile app.py -n flask-app-exec
                    //     ls -lh dist/flask-app-exec  // Verify executable
                    // '''
                }
            }
        }

        stage('Test on Docker') {
            steps {
                script {
                    // Start all services in the background
                    sh "docker compose -f ${COMPOSE_FILE} up -d"
                    // Wait for services to initialize (web, redis, db)
                    sh "sleep 30"
                    // Show running containers for debugging
                    sh "docker ps"
                    // Run tests inside the web container
                    sh "docker compose -f ${COMPOSE_FILE} exec -T web python3 /code/test.py"
                }
            }
            post {
                always {
                    // Clean up: stop and remove containers, volumes
                    sh "docker compose -f ${COMPOSE_FILE} down --volumes"
                }
            }
        }

        // stage('Build Package') {
        //     steps {
        //         script {
        //             // Create tarball including executable, source, and compose file
        //             sh '''
        //                 tar -czvf ${PACKAGE_NAME} \
        //                     dist/flask-app-exec \
        //                     app.py \
        //                     unittest.py \
        //                     docker-compose.yml
        //             '''
        //         }
        //     }
        // }

        // stage('Deliver to VM') {
        //     steps {
        //         sshagent(['vm-ssh-credentials']) { // Use Jenkins credentials for SSH
        //             sh '''
        //                 scp ${PACKAGE_NAME} ${VM_USER}@${VM_HOST}:/home/${VM_USER}/
        //             '''
        //         }
        //     }
        // }

        // stage('Test Again on VM') {
        //     steps {
        //         sshagent(['vm-ssh-credentials']) {
        //             sh '''
        //                 ssh ${VM_USER}@${VM_HOST} "
        //                     tar -xzvf /home/${VM_USER}/${PACKAGE_NAME} -C /home/${VM_USER}/app &&
        //                     cd /home/${VM_USER}/app &&
        //                     docker-compose up -d &&
        //                     sleep 10 &&
        //                     docker-compose exec -T web python3 /code/unittest.py &&
        //                     docker ps
        //                 "
        //             '''
        //         }
        //     }
        //     post {
        //         always {
        //             sshagent(['vm-ssh-credentials']) {
        //                 sh '''
        //                     ssh ${VM_USER}@${VM_HOST} ""
        //                 '''
        //             }
        //         }
        //     }
        // }
    }

    post {
        success {
            echo 'Pipeline completed successfully!'
        }
        failure {
            echo 'Pipeline failed. Check logs for details.'
        }
        always {
            // Clean up local workspace
            sh 'docker system prune -f || true' // Remove unused Docker objects
            cleanWs() // Clean Jenkins workspace
        }
    }
}