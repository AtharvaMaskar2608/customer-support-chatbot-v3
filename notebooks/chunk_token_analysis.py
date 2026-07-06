import tiktoken
import pandas as pd

def count_tokens(chunk : str, model_name = "gpt-4o") -> int:
    # Load the correct encoding for the model
    encoding = tiktoken.encoding_for_model(model_name)
    # Encode text to a list of tokens
    tokens = encoding.encode(chunk)
    return len(tokens)

df = pd.read_csv("./data/kb_faq_clean.csv")

chunks = df['chunk']

chunk_lens = [count_tokens(chunk) for chunk in chunks]

# max
print(f"Max : {max(chunk_lens)}")
print(f"Mean : {sum(chunk_lens) / len(chunk_lens)}")