# SDN_APIserv_demo


Project structure:
```shell
.
├── Dockerfile
├── README.md
├── app.py
├── compose.yaml
└── requirements.txt
```


compose.yaml
```shell
services:
   redis: 
     image: redislabs/redismod
     ports:
       - '6379:6379' 
   web:
        build: .
        ports:
            - "8000:8000"
        volumes:
            - .:/code
        depends_on:
            - redis
```

## Deploy with docker compose
```shell
$ docker compose up -d
[+] Running 24/24
 ⠿ redis Pulled   
 ...
⠿ 565225d89260 Pull complete
[+] Building 12.7s (10/10) FINISHED
 => [internal] load build definition from Dockerfile...
[+] Running 3/3
 ⠿ Network flask-redis_default    Created
 ⠿ Container flask-redis-redis-1  Started                                                                                                                                                                                     ⠿ Container flask-redis-web-1    Started
Expected result
Listing containers must show one container running and the port mapping as below:
$ docker compose ps
NAME                  COMMAND                  SERVICE             STATUS              PORTS
flask-redis-redis-1   "redis-server --load…"   redis               running             0.0.0.0:6379->6379/tcp
flask-redis-web-1     "/bin/sh -c 'python …"   web                 running             0.0.0.0:8000->8000/tcp
```

## Shutdown with docker compose
```shell
$ docker compose down
```
