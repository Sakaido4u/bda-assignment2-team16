FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy
COPY wheels /wheels
RUN pip install --no-index --find-links /wheels playwright==1.48.0
