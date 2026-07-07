"""Mock adapter for testing Cogscope without real LLM calls."""

import random
import time
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Iterator, Optional

from cogscope.capture.adapters.base import BaseAdapter, StreamChunk
from cogscope.core.models import ModelConfig, ReasoningTrace, TokenUsage, ToolCall


class MockAdapter(BaseAdapter):
    """Mock adapter for testing and development.

    This adapter simulates LLM behavior with configurable patterns.
    It's essential for:
    - Unit testing without API calls
    - Demonstrating Cogscope features
    - Simulating behavioral drift
    """

    adapter_type: str = "mock"

    # Behavioral presets for simulating different reasoning patterns
    PRESETS = {
        "default": {
            "depth": 3,
            "tool_probability": 0.3,
            "correction_probability": 0.2,
            "uncertainty_probability": 0.3,
            "verbosity": 1.0,
        },
        "verbose": {
            "depth": 5,
            "tool_probability": 0.4,
            "correction_probability": 0.3,
            "uncertainty_probability": 0.4,
            "verbosity": 2.0,
        },
        "terse": {
            "depth": 2,
            "tool_probability": 0.1,
            "correction_probability": 0.1,
            "uncertainty_probability": 0.1,
            "verbosity": 0.5,
        },
        "tool_heavy": {
            "depth": 4,
            "tool_probability": 0.8,
            "correction_probability": 0.2,
            "uncertainty_probability": 0.2,
            "verbosity": 1.0,
        },
        "uncertain": {
            "depth": 4,
            "tool_probability": 0.3,
            "correction_probability": 0.5,
            "uncertainty_probability": 0.7,
            "verbosity": 1.5,
        },
        "confident": {
            "depth": 3,
            "tool_probability": 0.2,
            "correction_probability": 0.05,
            "uncertainty_probability": 0.05,
            "verbosity": 0.8,
        },
    }

    # Sample tools for simulation
    SAMPLE_TOOLS = [
        "search_web",
        "execute_code",
        "read_file",
        "write_file",
        "query_database",
        "call_api",
        "analyze_image",
        "calculate",
    ]

    def __init__(
        self,
        model: str = "mock-model",
        preset: str = "default",
        seed: Optional[int] = None,
        **kwargs: Any,
    ):
        super().__init__(model, **kwargs)
        self.preset_name = preset
        self.preset = self.PRESETS.get(preset, self.PRESETS["default"])
        self.seed = seed
        if seed is not None:
            random.seed(seed)

    async def call(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Generate a mock trace asynchronously."""
        return self._generate_trace(prompt, system_message, messages, tools, task_id)

    def call_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Generate a mock trace synchronously."""
        return self._generate_trace(prompt, system_message, messages, tools, task_id)

    async def call_stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Generate a mock streaming response.

        Simulates token-by-token delivery for testing streaming consumers.
        """
        trace = self._generate_trace(prompt, system_message, messages, tools, task_id)

        # Yield reasoning in chunks
        if trace.reasoning_content:
            words = trace.reasoning_content.split()
            for i in range(0, len(words), 3):
                chunk_text = " ".join(words[i : i + 3]) + " "
                yield StreamChunk(
                    reasoning_text=chunk_text,
                    is_final=False,
                )

        # Yield output in chunks
        words = trace.output.split()
        for i in range(0, len(words), 3):
            chunk_text = " ".join(words[i : i + 3]) + " "
            yield StreamChunk(
                text=chunk_text,
                is_final=False,
            )

        # Final chunk with trace
        yield StreamChunk(
            text="",
            is_final=True,
            finish_reason=trace.finish_reason,
            metadata={
                "trace": trace,
                "full_text": trace.output,
                "reasoning_text": trace.reasoning_content or "",
            },
        )

    def call_stream_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Generate a mock synchronous streaming response."""
        trace = self._generate_trace(prompt, system_message, messages, tools, task_id)

        # Yield reasoning in chunks
        if trace.reasoning_content:
            words = trace.reasoning_content.split()
            for i in range(0, len(words), 3):
                chunk_text = " ".join(words[i : i + 3]) + " "
                yield StreamChunk(
                    reasoning_text=chunk_text,
                    is_final=False,
                )

        # Yield output in chunks
        words = trace.output.split()
        for i in range(0, len(words), 3):
            chunk_text = " ".join(words[i : i + 3]) + " "
            yield StreamChunk(
                text=chunk_text,
                is_final=False,
            )

        # Final chunk with trace
        yield StreamChunk(
            text="",
            is_final=True,
            finish_reason=trace.finish_reason,
            metadata={
                "trace": trace,
                "full_text": trace.output,
                "reasoning_text": trace.reasoning_content or "",
            },
        )

    def _generate_trace(
        self,
        prompt: str,
        system_message: Optional[str],
        messages: Optional[list[dict[str, Any]]],
        tools: Optional[list[dict[str, Any]]],
        task_id: str,
    ) -> ReasoningTrace:
        """Generate a complete mock reasoning trace."""
        start_time = time.time()

        # Generate reasoning chain
        reasoning_steps, reasoning_content = self._generate_reasoning(prompt)

        # Generate tool calls
        tool_calls = self._generate_tool_calls(tools)

        # Generate output
        output = self._generate_output(prompt, reasoning_steps, tool_calls)

        # Simulate latency
        simulated_latency = random.uniform(100, 500) * self.preset["verbosity"]
        time.sleep(min(simulated_latency / 1000, 0.1))  # Cap at 100ms for tests

        latency_ms = (time.time() - start_time) * 1000

        # Build messages list
        msg_list = []
        if system_message:
            msg_list.append({"role": "system", "content": system_message})
        if messages:
            msg_list.extend(messages)
        msg_list.append({"role": "user", "content": prompt})

        # Estimate tokens
        prompt_tokens = len(prompt.split()) * 4  # Rough estimate
        reasoning_tokens = len(reasoning_content.split()) * 4
        output_tokens = len(output.split()) * 4

        return ReasoningTrace(
            id=self._create_trace_id(task_id),
            task_id=task_id,
            model=self.model,
            model_config_params=self.config,
            adapter_type=self.adapter_type,
            system_message=system_message,
            prompt=prompt,
            messages=msg_list,
            tool_calls=tool_calls,
            reasoning_tokens=reasoning_steps,
            reasoning_content=reasoning_content,
            output=output,
            finish_reason="stop",
            latency_ms=latency_ms,
            token_usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=output_tokens + reasoning_tokens,
                total_tokens=prompt_tokens + output_tokens + reasoning_tokens,
                reasoning_tokens=reasoning_tokens,
            ),
            metadata={
                "preset": self.preset_name,
                "mock": True,
            },
        )

    def _generate_reasoning(self, prompt: str) -> tuple[list[str], str]:
        """Generate mock reasoning steps."""
        depth = self.preset["depth"]
        steps = []

        # Add variation based on config
        actual_depth = max(1, depth + random.randint(-1, 1))

        reasoning_templates = [
            "Let me analyze the request: {}",
            "First, I'll consider the key aspects...",
            "Breaking this down into steps:",
            "The main challenge here is to {}",
            "I need to think about this carefully.",
            "Step {}: {}",
            "Let me verify my understanding...",
            "Considering the constraints...",
            "This requires a systematic approach.",
        ]

        correction_templates = [
            "Wait, let me reconsider that.",
            "Actually, I should approach this differently.",
            "Hmm, that's not quite right.",
            "Let me correct that assumption.",
        ]

        uncertainty_templates = [
            "I'm not entirely sure, but...",
            "This might require further analysis.",
            "It's possible that...",
            "I think, though I'm uncertain...",
        ]

        confidence_templates = [
            "I'm confident that...",
            "Clearly, the answer is...",
            "This is definitely the right approach.",
            "Without doubt,...",
        ]

        for i in range(actual_depth):
            # Add main step
            template = random.choice(reasoning_templates)
            step = template.format(prompt[:50], i + 1, f"analyzing step {i + 1}")
            steps.append(step)

            # Maybe add correction
            if random.random() < self.preset["correction_probability"]:
                steps.append(random.choice(correction_templates))

            # Maybe add uncertainty
            if random.random() < self.preset["uncertainty_probability"]:
                steps.append(random.choice(uncertainty_templates))
            elif random.random() > self.preset["uncertainty_probability"] * 2:
                steps.append(random.choice(confidence_templates))

        # Add verification step
        if random.random() > 0.5:
            steps.append("Let me verify this reasoning is correct...")
            steps.append("Yes, this approach should work.")

        reasoning_content = "\n".join(steps)
        return steps, reasoning_content

    def _generate_tool_calls(self, tools: Optional[list[dict[str, Any]]]) -> list[ToolCall]:
        """Generate mock tool calls."""
        tool_calls = []

        # Determine number of tool calls
        if random.random() < self.preset["tool_probability"]:
            num_calls = random.randint(1, 4)

            available_tools = self.SAMPLE_TOOLS
            if tools:
                available_tools = [
                    t.get("function", {}).get("name", t.get("name", "unknown")) for t in tools
                ]
                if not available_tools:
                    available_tools = self.SAMPLE_TOOLS

            for i in range(num_calls):
                tool_name = random.choice(available_tools)
                tool_calls.append(
                    ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name=tool_name,
                        arguments={"query": f"mock query {i + 1}"},
                        result=f"Mock result for {tool_name}",
                        duration_ms=random.uniform(50, 200),
                    )
                )

        return tool_calls

    def _generate_output(
        self,
        prompt: str,
        reasoning_steps: list[str],
        tool_calls: list[ToolCall],
    ) -> str:
        """Generate mock output."""
        output_templates = [
            "Based on my analysis, {result}",
            "After considering all factors, here's the answer: {result}",
            "The solution is: {result}",
            "{result}\n\nI hope this helps!",
            "Here's what I found:\n\n{result}",
        ]

        # Generate result based on prompt
        words = prompt.split()[:10]
        result = f"This is a mock response to: {' '.join(words)}..."

        # Add tool results if any
        if tool_calls:
            result += f"\n\nI used {len(tool_calls)} tools to assist with this."
            for tc in tool_calls:
                result += f"\n- {tc.name}: {tc.result}"

        # Add connection to reasoning
        if len(reasoning_steps) > 2:
            result += f"\n\nMy reasoning involved {len(reasoning_steps)} main steps."

        # Apply verbosity
        if self.preset["verbosity"] > 1:
            result += "\n\nLet me elaborate further on the key points..."
            result += "\n" + "\n".join([f"- Point {i+1}" for i in range(3)])

        template = random.choice(output_templates)
        return template.format(result=result)

    def set_preset(self, preset_name: str) -> None:
        """Change the behavioral preset."""
        if preset_name in self.PRESETS:
            self.preset_name = preset_name
            self.preset = self.PRESETS[preset_name]
        else:
            raise ValueError(
                f"Unknown preset: {preset_name}. Available: {list(self.PRESETS.keys())}"
            )

    def customize_preset(self, **kwargs: Any) -> None:
        """Customize the current preset."""
        self.preset.update(kwargs)
        self.preset_name = "custom"
