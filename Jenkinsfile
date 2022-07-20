pipeline {
    agent any
    stages {
        stage('clean-pre') {
            steps {
                sh "make clean"
            }
        }
        stage('cq') {
            steps {
                sh "make cq"
            }
        }
        stage('sonarqube') {
            steps {
                script {
                    scannerHome = tool 'SonarQube Scanner'
                }
                withEnv(["JAVA_HOME=/apps/java/latest"]) {
                    withSonarQubeEnv('Campaign SonarQube') {
                        dir('.') {
                            sh "${scannerHome}/bin/sonar-scanner"
                        }
                    }
                }
            }
        }
        stage('build') {
            steps {
                sh "make build"
            }
        }
        stage('clean-post') {
            steps {
                sh "make clean"
            }
        }
    }
}
