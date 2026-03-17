FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

# 依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY evidence_runner.py .
COPY project_config.py .
COPY create_template.py .

# 作業ディレクトリ（仕様書・設定ファイル・出力先をマウントする想定）
VOLUME ["/work"]
WORKDIR /work

ENTRYPOINT ["python", "/app/evidence_runner.py"]
