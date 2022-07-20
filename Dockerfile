FROM imagename:
RUN        apk update &&\
           apk add --no-cache ca-certificates &&\
           rm -rf /var/cache/apk/*
COPY       release/inventory-svc-linux* /bin/inventory-svc
ENTRYPOINT [ "/bin/inventory-svc" ]
