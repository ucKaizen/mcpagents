from transformers import pipeline

# Initialize NER pipeline
ner = pipeline("token-classification", 
               model="dslim/bert-base-NER",
               aggregation_strategy="simple")

def add_context(text):
    """Add product context hints to improve NER detection"""
    product_keywords = ["z-fold", "iphone", "galaxy", "pixel"]
    
    # Check if text contains product keywords
    if any(keyword in text.lower() for keyword in product_keywords):
        return f"Product Review: In this tech review of the {text}"
    return text

# Test texts with various entity types
texts = [
    "I love apple products like the iPhone and MacBook.",
    "I buy healthy stuff from supermaets like apple and banana.",
    "Samsung Galaxy Z Fold 7 battery review",  # Added more structured product name
]

def demo_ner(text):
    print("\n" + "="*60)
    print(f"Original: {text}")
    
    # Add context before processing
    text_with_context = add_context(text)
    print(f"With Context: {text_with_context}")
    print("-"*60)
    
    entities = ner(text_with_context)
    for entity in entities:
        print(f"Entity: {entity['word']}")
        print(f"Type: {entity['entity_group']}")
        print(f"Confidence: {entity['score']:.3f}")
        print("-"*30)

def main():
    print("NER Demo - Enhanced Product Detection\n")
    for text in texts:
        demo_ner(text)

if __name__ == "__main__":
    main()