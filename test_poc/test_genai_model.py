#### https://medium.com/@scholarly360/mistral-7b-complete-guide-on-colab-129fa5e9a04d

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from transformers import BitsAndBytesConfig
from langchain import HuggingFacePipeline
from langchain import PromptTemplate, LLMChain

# Quantize 🤗 Transformers models
quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
)

# define Mistral AI Large Language Models
model_id = "mistralai/Mistral-7B-Instruct-v0.1"
model_4bit = AutoModelForCausalLM.from_pretrained( model_id, device_map="auto",quantization_config=quantization_config, )
tokenizer = AutoTokenizer.from_pretrained(model_id)

pipeline = pipeline(
        "text-generation",
        model=model_4bit,
        tokenizer=tokenizer,
        use_cache=True,
        device_map="auto",
        max_length=500,
        do_sample=True,
        top_k=5,
        num_return_sequences=1,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.eos_token_id,
)

#### Prompt 1
context_p1 = """ Transform Your Business with LEO CDP. Customer Data platform for omnichannel personalization, is developed by USPA Technology Company"""
question_p1 = """What is the technology to build omnichannel personalization for our customer ?"""
template1 = """<s>[INST] You are a helpful, respectful and honest assistant. Answer exactly in few words from the context
Answer the question below from context below :
{context}
{question} [/INST] </s>
"""
prompt1 = PromptTemplate(template=template1, input_variables=["question","context"])

#### Prompt 2
context_p2 = """ In Retail Industry """
question_p2 = """ What is the marketing plan to grow customer lifetime value ? """
template2 = """<s>[INST] You are the marketing manager. :
{context}
{question} [/INST] </s>
"""
prompt2 = PromptTemplate(template=template2, input_variables=["question","context"])

#### Prompt 3
context_p3 = """ In Culture and Movie Industry, """
question_p3 = """ Write a marketing plan to promote a movie ? """
template3 = """<s>[INST] You are the marketing manager. Answer less than 5000 words, from the context :
{context}
{question} [/INST] </s>
"""
prompt3 = PromptTemplate(template=template3, input_variables=["question","context"])

# set pipeline into LLMChain with prompt and llm model
llm = HuggingFacePipeline(pipeline=pipeline)
llm_chain = LLMChain(prompt=prompt3, llm=llm)
response = llm_chain.run({"question":question_p3,"context":context_p3})

print(response)