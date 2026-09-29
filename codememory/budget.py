import os

class Budget:
    def __init__(self):
        self.max_llm_calls = int(os.getenv('MAX_LLM_CALLS', 120))
        self.max_llm_tokens = int(os.getenv('MAX_LLM_TOKENS', 150000))
        
        # From amendment
        daily_reqs = int(os.getenv('HINDSIGHT_LLM_DAILY_REQUESTS', 15))
        self.max_retains = min(int(os.getenv('MAX_RETAINS', 40)), daily_reqs - 3)
        self.max_reflects = min(int(os.getenv('MAX_REFLECTS', 5)), 1)
        self.max_recalls = int(os.getenv('MAX_RECALLS', 120))
        
        self.groq_tpm = int(os.getenv('GROQ_TPM', 5000))
        
        self.usage = {
            'llm_calls': 0,
            'llm_tokens': 0,
            'cache_hits': 0,
            'retains': 0,
            'recalls': 0,
            'reflects': 0
        }
    
    def check_llm(self, text):
        if self.usage['llm_calls'] >= self.max_llm_calls:
            raise RuntimeError("Budget exhausted: MAX_LLM_CALLS")
        estimated_tokens = len(text) // 4
        if self.usage['llm_tokens'] + estimated_tokens > self.max_llm_tokens:
            raise RuntimeError("Budget exhausted: MAX_LLM_TOKENS")
            
    def record_llm(self, usage_dict):
        self.usage['llm_calls'] += 1
        self.usage['llm_tokens'] += usage_dict.get('total_tokens', 0)
        
    def check_retain(self):
        if self.usage['retains'] >= self.max_retains:
            raise RuntimeError("Budget exhausted: MAX_RETAINS")
            
    def record_retain(self):
        self.usage['retains'] += 1
        
    def check_recall(self):
        if self.usage['recalls'] >= self.max_recalls:
            raise RuntimeError("Budget exhausted: MAX_RECALLS")
            
    def record_recall(self):
        self.usage['recalls'] += 1
        
    def check_reflect(self):
        if self.usage['reflects'] >= self.max_reflects:
            raise RuntimeError("Budget exhausted: MAX_REFLECTS")
            
    def record_reflect(self):
        self.usage['reflects'] += 1

global_budget = Budget()
