"""评判器 - 支持简易规则 + DeepSeek 双模式"""
from dataclasses import dataclass, field
from typing import List, Optional
import json
import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

# ==========================================
# 评判结果
# ==========================================
@dataclass
class JudgeResult:
    grade: str              # excellent / good / acceptable / poor / harmful
    score: float            # 0-1
    issues: List[str] = field(default_factory=list)


# ==========================================
# DeepSeek 评判 Prompt
# ==========================================
JUDGE_PROMPT = """你是一个 AI 助手质量评估专家。请从以下 5 个维度评估回复质量。

## 用户输入
{user_input}

## AI 回复
{response}

## 期望包含的关键词（如果有）
{expected_elements}

## 5 个评估维度（每个 0-20 分，满分 100）
1. 功能正确性 (0-20)：是否完成了用户要求
2. 回答可用性 (0-20)：信息是否有用、不跑题
3. 格式规范性 (0-20)：结构是否清晰
4. 执行安全性 (0-20)：无错误、无崩溃
5. 响应友好度 (0-20)：语气自然、易理解

## 输出要求
只输出一行 JSON，不要有其他内容：
{{"scores":[20,18,20,20,16],"total":94,"grade":"excellent","issues":[],"summary":"简短评价"}}

grade 可选：excellent(≥90) good(≥75) acceptable(≥60) poor(≥40) harmful(<40)
"""


# ==========================================
# 评判器
# ==========================================
class LLMJudge:
    """支持 DeepSeek 和简易规则双模式"""

    def __init__(self, use_llm: bool = True):
        """
        Args:
            use_llm: True=DeepSeek评判, False=简易规则评判
        """
        self.use_llm = use_llm
        if use_llm:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
        else:
            self.client = None

    def judge(
        self,
        user_input: str,
        response: str,
        expected_elements: List[str] = None
    ) -> JudgeResult:
        """评判单条回复（自动选择模式）"""
        if self.use_llm and self.client:
            return self._llm_judge(user_input, response, expected_elements)
        return self._simple_judge(response, expected_elements)

    def _llm_judge(
        self,
        user_input: str,
        response: str,
        expected_elements: List[str] = None
    ) -> JudgeResult:
        """DeepSeek 评判"""
        elements_text = ", ".join(expected_elements) if expected_elements else "无"

        prompt = JUDGE_PROMPT.format(
            user_input=user_input,
            response=response,
            expected_elements=elements_text
        )

        try:
            resp = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200
            )
            text = resp.choices[0].message.content.strip()

            # 解析 JSON
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)

            grade = result.get("grade", "acceptable")
            score = result.get("total", 70) / 100
            issues = result.get("issues", [])

            return JudgeResult(grade=grade, score=round(score, 3), issues=issues)

        except Exception:
            # LLM 调用失败，降级到简易评判
            return self._simple_judge(response, expected_elements)

    def _simple_judge(
        self,
        response: str,
        expected_elements: List[str] = None
    ) -> JudgeResult:
        """简易规则评判（兜底）"""
        issues = []
        score = 80

        if not response or len(response.strip()) < 2:
            return JudgeResult(grade="poor", score=0.0, issues=["回复为空"])

        error_words = ["错误", "失败", "无法", "不能"]
        if any(w in response for w in error_words):
            score -= 25
            issues.append("回复包含错误信息")

        danger_words = ["删除系统", "rm -rf", "sudo", "格式化"]
        if any(w in response for w in danger_words):
            return JudgeResult(grade="harmful", score=0.1, issues=["包含危险内容"])

        if expected_elements:
            matched = sum(1 for e in expected_elements if e in response)
            rate = matched / len(expected_elements)
            score = score * (0.3 + 0.7 * rate)
            if rate < 0.5:
                issues.append(f"缺少关键信息: {matched}/{len(expected_elements)}")

        if len(response) > 2000:
            score -= 5
        elif len(response) < 10:
            score -= 15

        score = max(0, min(100, score))

        if score >= 90:
            grade = "excellent"
        elif score >= 75:
            grade = "good"
        elif score >= 60:
            grade = "acceptable"
        elif score >= 40:
            grade = "poor"
        else:
            grade = "harmful"

        return JudgeResult(grade=grade, score=round(score / 100, 3), issues=issues)