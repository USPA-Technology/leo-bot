from sentence_transformers import SentenceTransformer, util

import os
import time
import torch
from redis import Redis

REDIS_USER_SESSION_HOST = os.getenv("REDIS_USER_SESSION_HOST")
REDIS_USER_SESSION_PORT = os.getenv("REDIS_USER_SESSION_PORT")
REDIS_CLIENT = Redis(host=REDIS_USER_SESSION_HOST, port=REDIS_USER_SESSION_PORT, decode_responses=True)

MODEL_NAME = 'sentence-transformers/msmarco-distilroberta-base-v2'
model = SentenceTransformer(MODEL_NAME)

# Corpus with example sentences
corpus_list = ['A man is eating food.',
          'A man is eating a piece of bread.',
          'The girl is carrying a baby.',
          'A man is riding a horse.',
          'A woman is playing violin.',
          'Two men pushed carts through the woods.',
          'A man is riding a white horse on an enclosed ground.',
          'A monkey is playing drums.',
          'A cheetah is running behind its prey.',
          'God is love.',
          'Love is everywhere.'
          ]

corpus_ids = []
corpus_embeddings = []

start = time.time()

enums = enumerate(corpus_list)
for id, corpus in enums:
    ids = str(id)
    print(ids + " = " + corpus)

    # 1.147646188735962
    #corpus_embedding = model.encode(corpus, convert_to_tensor=True)

    # 0.6244969367980957
    corpus_embedding = torch.load( './local_data/' + ids)

    corpus_embeddings.append(corpus_embedding)    
    corpus_ids.append(ids)
    
    #torch.save(corpus_embedding, './local_data/' + ids)

end = time.time()
print("=> execute ",end - start)

# Query sentences:
queries = ['Is love everywhere ?','A man is eating pasta.', 'Someone in a gorilla costume is playing a set of drums.', 'A cheetah chases prey on across a field.']

# Find the closest 5 sentences of the corpus_list for each query sentence based on cosine similarity
top_k = min(5, len(corpus_list))
for query in queries:
    query_embedding = model.encode(query, convert_to_tensor=True)

    print("\n\n======================\n\n")
    print("Query:", query)
    print("\nTop 5 most similar sentences in corpus_list:")

    # Alternatively, we can also use util.semantic_search to perform cosine similarty + topk
    hits = util.semantic_search(query_embedding, corpus_embeddings, top_k=top_k)
    hits = hits[0]      #Get the hits for the first query
    for hit in hits:
        corpus_id = hit['corpus_id']
        print("corpus_id: ", corpus_id)
        print(corpus_list[corpus_id], "(Score: {:.4f})".format(hit['score']))