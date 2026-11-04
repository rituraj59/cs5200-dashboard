# Restaurant Analytics Dashboard (CS5200 Practicum I, Part H)

Streamlit web app that reports on the live Aiven MySQL database.
All aggregation runs as SQL on the database; filters (years, restaurants,
meal types) are passed to the queries as parameters.

## Run locally
1. `pip install -r requirements.txt`
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
   and fill in the password.
3. `streamlit run app.py` and open http://localhost:8501

## Deploy (Streamlit Community Cloud, free)
1. Push this folder to a GitHub repository (secrets.toml is git-ignored).
2. On share.streamlit.io, choose "Create app", pick the repository and `app.py`.
3. Under Advanced settings -> Secrets, paste the content of
   `secrets.toml.example` with the real password, and deploy.

The Aiven free plan powers off after inactivity; if the dashboard shows a
connection error, start the service in the Aiven console and reload.
