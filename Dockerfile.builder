FROM golang:1 as builder
RUN mkdir /inventory
WORKDIR /inventory
CMD ["bash", "build.sh"]
