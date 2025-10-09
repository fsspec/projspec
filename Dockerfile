FROM python

# todo: exclude potentially large env directories
COPY . .
RUN pip install . --no-cache-dir
CMD ["projspec"]
