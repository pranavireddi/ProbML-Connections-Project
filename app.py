from flask import Flask, jsonify
from generator import PuzzleGenerator

app = Flask(__name__)
generator = PuzzleGenerator("processed_categories.json")

@app.get("/api/puzzle")
def get_puzzle():
    return jsonify(generator.generate_puzzle())