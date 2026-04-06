from flask import Flask, jsonify, redirect
from generator import PuzzleGenerator

app = Flask(__name__)
generator = PuzzleGenerator("processed_categories.json")

@app.get("/")
def home():
    return redirect("/index.html", code=307)

@app.get("/api/puzzle")
def get_puzzle():
    return jsonify(generator.generate_puzzle())

@app.get("/ping")
def ping():
    return {"ok": True}