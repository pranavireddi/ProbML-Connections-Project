from flask import Flask, jsonify, send_from_directory
from generator import PuzzleGenerator

app = Flask(__name__)
generator = PuzzleGenerator("processed_categories.json")

@app.get("/")
def home():
    return send_from_directory("public", "index.html")

@app.get("/api/puzzle")
def get_puzzle():
    return jsonify(generator.generate_puzzle())

@app.get("/ping")
def ping():
    return {"ok": True}