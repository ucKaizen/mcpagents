from transformers import pipeline

# Initialize NER pipeline
ner = pipeline("token-classification", 
               model="dslim/bert-base-NER",
               aggregation_strategy="simple")

# Test texts with various entity types
texts = [
    "I love apple products like the iPhone and MacBook.",
    "I buy healthy stuff from supermaets like apple and banana.",
    "Samsung Galaxy Z Fold 7 battery review",  # Added more structured product name
]

def demo_ner(text):
    entities = ner(text)
    print(f"Text: {text}")
    brand_found = False

    for entity in entities:
        if entity['entity_group'] in ['ORG', 'MISC']:
            print(f"Detected Brand: {entity['word']} ({entity['entity_group']}, {entity['score']:.2f})")
            brand_found = True

    if not brand_found:
        print("Detected Brand: Undetected")

    print("-" * 40)

def main():
    print("NER Demo - Enhanced Product Detection\n")
    for text in texts:
        demo_ner(text)

if __name__ == "__main__":
    main()