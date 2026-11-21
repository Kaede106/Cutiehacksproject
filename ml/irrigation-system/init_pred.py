import joblib

def predict(moisture, temperature, humidity):
    # sys.executable ensures it uses the exact same Python environment
    loaded_model = joblib.load("logistic_model.joblib")
    return loaded_model.predict([[temperature, humidity, moisture]])[0]