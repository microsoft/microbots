import json
import os
from dataclasses import asdict

from dotenv import load_dotenv
from openai import OpenAI
from microbots.llm.llm import LLMAskResponse, LLMInterface

load_dotenv()

endpoint = os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1")
api_key = os.getenv("OPENAI_API_KEY")


class OpenAIApi(LLMInterface):

    def __init__(self, system_prompt, deployment_name, max_retries=3):
        if not api_key:
            raise ValueError(
                "No authentication configured for OpenAI. "
                "Set the OPENAI_API_KEY environment variable."
            )

        self.ai_client = OpenAI(
            base_url=endpoint,
            api_key=api_key,
        )
        self.deployment_name = deployment_name
        self.system_prompt = system_prompt
        self.messages = [{"role": "system", "content": system_prompt}]

        self.max_retries = max_retries
        self.retries = 0

    def ask(self, message) -> LLMAskResponse:
        self.retries = 0

        self.messages.append({"role": "user", "content": message})

        valid = False
        while not valid:
            response = self.ai_client.responses.create(
                model=self.deployment_name,
                input=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.output_text})
            valid, askResponse = self._validate_llm_response(response=response.output_text)

        # Remove last assistant message and replace with structured response
        self.messages.pop()
        self.messages.append({"role": "assistant", "content": json.dumps(asdict(askResponse))})

        return askResponse

    def clear_history(self):
        self.messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            }
        ]
        return True
