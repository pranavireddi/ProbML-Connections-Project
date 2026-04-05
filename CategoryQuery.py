from SPARQLWrapper import SPARQLWrapper, JSON
import re
import random
import sys

def get_blue_group(property_short, object_short, limit=4):
    sparql = SPARQLWrapper("https://dbpedia.org/sparql")
    
    # Comprehensive prefix list to prevent "unbound prefix" errors
    query = f"""
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX dbr: <http://dbpedia.org/resource/>
    PREFIX dbc: <http://dbpedia.org/resource/Category:>
    PREFIX dct: <http://purl.org/dc/terms/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?label WHERE {{
      ?item {property_short} {object_short} .
      ?item rdfs:label ?label .
      FILTER (lang(?label) = "en")
    }}
    LIMIT 100
    """
    
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    
    try:
        results = sparql.query().convert()
        raw_labels = [result['label']['value'] for result in results["results"]["bindings"]]
        
        clean_labels = []
        for label in raw_labels:
            # Clean: "Mercury (element)" -> "MERCURY"
            name = re.sub(r'\s*\([^)]*\)', '', label).strip().upper()
            
            # Connections likes single words. Filter out phrases for now.
            if " " not in name and name.isalpha():
                if name not in clean_labels:
                    clean_labels.append(name)
        
        return clean_labels[:limit]

    except Exception as e:
        return [f"Error: {e}"]

# # --- TEST CALLS WITH CORRECTED MAPPINGS ---

# # 1. Noble Gases (Using Categories is more reliable for Blue)
# print("Noble Gases:", get_blue_group("dct:subject", "dbc:Noble_gases"))

# # 2. Moons (Astronomy) - Using dbo:parentAdlerian/Orbiting
# print("Jupiter Moons:", get_blue_group("dct:subject", "dbc:Moons_of_Jupiter"))

# # 3. Chess Pieces (Specific Knowledge)
# print("Chess Pieces:", get_blue_group("dct:subject", "dbc:Chess_pieces"))

def get_top_level_topics():
    sparql = SPARQLWrapper("https://dbpedia.org/sparql")
    query = """
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX dbc: <http://dbpedia.org/resource/Category:>

    SELECT DISTINCT ?top_cat ?label WHERE {
      # We start from 'Main_topic_classifications' to get high-quality pillars
      ?top_cat skos:broader dbc:Main_topic_classifications .
      ?top_cat rdfs:label ?label .
      FILTER (lang(?label) = "en")
    }
    ORDER BY ?label
    """
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return [r['label']['value'] for r in results["results"]["bindings"]]

def get_random_subcategory(parent_category):
    sparql = SPARQLWrapper("https://dbpedia.org/sparql")
    
    # query explanation:
    # 1. Look for categories (?sub) that have our parent as their broader category.
    # 2. We use skos:broader because DBpedia links 'child -> parent'.
    query = f"""
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX dbc: <http://dbpedia.org/resource/Category:>
    
    SELECT DISTINCT ?sub WHERE {{
      ?sub skos:broader {parent_category} .
    }}
    LIMIT 50
    """
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    
    subs = [r['sub']['value'].replace("http://dbpedia.org/resource/", "") for r in results["results"]["bindings"]]
    # Return a random choice if any exist, otherwise return None
    return "dbc:" + random.choice(subs).split(':')[-1] if subs else None

def get_random_subcategory_weighted(parent_category):
    """
    Modified to find subcategories and count their children.
    We prefer subcategories that have MORE children (breadth).
    """
    sparql = SPARQLWrapper("https://dbpedia.org/sparql")
    
    # This query finds subcategories AND counts how many children THEY have.
    query = f"""
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX dbc: <http://dbpedia.org/resource/Category:>
    
    SELECT ?sub (COUNT(?grandchild) AS ?childCount) WHERE {{
      ?sub skos:broader {parent_category} .
      OPTIONAL {{ ?grandchild skos:broader ?sub . }}
    }}
    GROUP BY ?sub
    HAVING (COUNT(?grandchild) > 5)  # Pruning: Only keep 'large' subcategories
    LIMIT 20
    """
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    
    bindings = results["results"]["bindings"]
    if not bindings:
        return None
    
    # Instead of random.choice, we pick from the ones with the most children
    # to ensure we stay in 'fertile' parts of the tree.
    sorted_subs = sorted(bindings, key=lambda x: int(x['childCount']['value']), reverse=True)
    
    # Pick from the top 3 most "populous" subcategories
    choice = random.choice(sorted_subs[:3])
    sub_uri = choice['sub']['value'].replace("http://dbpedia.org/resource/", "")
    return "dbc:" + sub_uri.split(':')[-1]

def find_viable_blue_category(seed_category, depth=3):
    current = seed_category
    print(f"Starting crawl from {current}...")
    
    for i in range(depth):
        # 1. Get a child of the current category
        next_cat = get_random_subcategory_weighted(current)
        
        if next_cat:
            # 2. Check if this sub-category has 'Blue-sized' potential (4-15 items)
            # We reuse your logic here to see how many single-word items it has
            potential_members = get_blue_group("dct:subject", next_cat, limit=4)
            
            count = len(potential_members)
            print(f"  Checked {next_cat}: found {count} valid words.")
            
            if 4 <= count <= 12:
                return next_cat, potential_members
            
            current = next_cat # Drill deeper
        else:
            break
            
    return None, None


def main():
    num_categories = sys.argv[1]

    # Pick one of the super categories
    super_categories = [f"dbc:{cat}" for cat in get_top_level_topics()]

    ## run until a successful category is found
    for i in range(1, int(num_categories)+1):
        while True:
            seed = random.choice(super_categories)
            cat_name, words = find_viable_blue_category(seed)
            if cat_name:
                print(f"\nSUCCESS! Found Category: {cat_name}")
                print(f"Words: {words}")

                # save to file in .json format
                with open(f"categories/{cat_name}.json", "a") as f:
                    f.write(f"{words}\n")
                break
            else:
                print("\nCould not find a perfect sized category this time. Try again!")

if __name__ == "__main__":
    main()