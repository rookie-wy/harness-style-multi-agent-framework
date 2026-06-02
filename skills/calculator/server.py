"""Calculator Skill - FastAPI 微服务（栈实现后缀表达式计算）"""
from fastapi import FastAPI
from pydantic import BaseModel
import time
import re
import operator

app = FastAPI(title="Calculator Skill")


# ==========================================
# 栈实现的后缀表达式计算器
# ==========================================
class ExpressionCalculator:
    """基于栈的表达式计算器，支持 + - * / % ^ ( )"""

    PRECEDENCE = {
        '+': 1, '-': 1,
        '*': 2, '/': 2, '%': 2,
        '^': 3,
    }

    RIGHT_ASSOCIATIVE = {'^'}

    def calculate(self, expression: str, precision: int = 10) -> float:
        postfix = self._infix_to_postfix(expression)
        result = self._evaluate_postfix(postfix)
        return round(result, precision)

    def _infix_to_postfix(self, expression: str) -> list:
        output = []
        operators = []

        i = 0
        while i < len(expression):
            char = expression[i]

            if char == ' ':
                i += 1
                continue

            # 数字（包括小数）
            if char.isdigit() or (char == '.' and i + 1 < len(expression) and expression[i + 1].isdigit()):
                num_str = ''
                while i < len(expression) and (expression[i].isdigit() or expression[i] == '.'):
                    num_str += expression[i]
                    i += 1
                if num_str.count('.') > 1:
                    raise ValueError(f"无效数字: {num_str}")
                output.append(float(num_str) if '.' in num_str else int(num_str))
                continue

            # 左括号
            elif char == '(':
                operators.append(char)

            # 右括号
            elif char == ')':
                while operators and operators[-1] != '(':
                    output.append(operators.pop())
                if not operators:
                    raise ValueError("括号不匹配：多余的右括号")
                operators.pop()

            # 负号（表达式开头或左括号后）
            elif char == '-' and (i == 0 or expression[i - 1] == '(' or expression[i - 1] in self.PRECEDENCE):
                i += 1
                num_str = '-'
                while i < len(expression) and (expression[i].isdigit() or expression[i] == '.'):
                    num_str += expression[i]
                    i += 1
                if num_str == '-':
                    raise ValueError("负号后缺少数字")
                if num_str.count('.') > 1:
                    raise ValueError(f"无效数字: {num_str}")
                output.append(float(num_str) if '.' in num_str else int(num_str))
                continue

            # 运算符
            elif char in self.PRECEDENCE:
                while (operators and operators[-1] != '(' and
                       (self.PRECEDENCE[operators[-1]] > self.PRECEDENCE[char] or
                        (self.PRECEDENCE[operators[-1]] == self.PRECEDENCE[char] and
                         char not in self.RIGHT_ASSOCIATIVE))):
                    output.append(operators.pop())
                operators.append(char)

            else:
                raise ValueError(f"非法字符: '{char}'")

            i += 1

        while operators:
            op = operators.pop()
            if op == '(':
                raise ValueError("括号不匹配：多余的左括号")
            output.append(op)

        return output

    def _evaluate_postfix(self, postfix: list) -> float:
        stack = []

        for token in postfix:
            if isinstance(token, (int, float)):
                stack.append(token)
            elif token in self.PRECEDENCE:
                if len(stack) < 2:
                    raise ValueError(f"运算符 '{token}' 缺少操作数")
                b = stack.pop()
                a = stack.pop()
                result = self._apply_operator(a, token, b)
                stack.append(result)
            else:
                raise ValueError(f"无效的后缀元素: {token}")

        if len(stack) != 1:
            raise ValueError("表达式计算异常")

        return stack[0]

    def _apply_operator(self, a: float, op: str, b: float) -> float:
        if op == '+':
            return a + b
        elif op == '-':
            return a - b
        elif op == '*':
            return a * b
        elif op == '/':
            if b == 0:
                raise ZeroDivisionError("除数不能为零")
            return a / b
        elif op == '%':
            if b == 0:
                raise ZeroDivisionError("取模运算除数不能为零")
            return a % b
        elif op == '^':
            return a ** b
        else:
            raise ValueError(f"未知运算符: {op}")


calculator = ExpressionCalculator()


# ==========================================
# 请求模型
# ==========================================
class ExecuteRequest(BaseModel):
    params: dict = {}
    user_input: str = ""


# ==========================================
# 表达式提取
# ==========================================
def extract_expression(text: str) -> str:
    """从用户输入中提取数学表达式"""
    # 移除常见前缀
    for prefix in ["计算一下", "计算", "算一下", "等于多少", "帮我算", "算", "等于", "等于几"]:
        text = text.replace(prefix, "")

    # 全角转半角
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("×", "*").replace("÷", "/")
    text = text.replace("＋", "+").replace("－", "-")

    # 保留合法字符
    allowed = set("0123456789+-*/().%^ ")
    chars = [c for c in text if c in allowed]

    result = "".join(chars).strip()

    # 去掉末尾多余的运算符
    while result and result[-1] in "+-*/%^":
        result = result[:-1]

    return result


# ==========================================
# API 端点
# ==========================================
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "skill": "calculator",
        "version": "2.0.0",
        "features": ["四则运算", "括号", "幂运算", "取模", "小数"]
    }


@app.post("/execute")
async def execute(request: ExecuteRequest):
    start = time.time()

    # 1. 提取表达式
    expression = request.params.get("expression", "")
    if not expression:
        expression = extract_expression(request.user_input)

    precision = request.params.get("precision", 10)

    # 2. 校验
    if not expression:
        return _build_response(
            status="error", error_code="INVALID_PARAMS",
            display="未找到有效的数学表达式",
            hints=["请提供算式，如: 3+(5-2)*4", "支持 + - * / % ^ ( )"],
            start=start
        )

    if len(expression) > 500:
        return _build_response(
            status="error", error_code="INVALID_PARAMS",
            display="表达式过长",
            hints=["请缩短表达式"],
            start=start
        )

    if not re.match(r'^[0-9+\-*/().%\^\s]+$', expression):
        allowed_set = set("0123456789+-*/().%^ ")
        illegal = set(expression) - allowed_set - {' '}
        return _build_response(
            status="error", error_code="INVALID_PARAMS",
            display=f"表达式包含非法字符: {', '.join(illegal)}",
            hints=["支持的运算符: + - * / % ^", "支持括号: ( )"],
            start=start
        )

    # 3. 计算
    try:
        result = calculator.calculate(expression, precision)

        if result == int(result):
            display_result = str(int(result))
        else:
            display_result = str(result)

        return _build_response(
            status="success",
            data={"expression": expression, "result": result, "precision": precision},
            display=f"{expression} = {display_result}",
            start=start
        )

    except ZeroDivisionError:
        return _build_response(
            status="error", error_code="DIVISION_BY_ZERO",
            display="除数不能为零",
            hints=["请检查表达式中的除法运算"],
            start=start
        )

    except ValueError as e:
        return _build_response(
            status="error", error_code="INVALID_EXPRESSION",
            display=f"表达式格式错误: {str(e)}",
            hints=["请检查括号是否匹配", "请检查运算符是否正确"],
            start=start
        )

    except Exception as e:
        return _build_response(
            status="error", error_code="EXECUTION_FAILED",
            display=f"计算失败: {str(e)}",
            hints=["请检查表达式格式"],
            start=start
        )


def _build_response(status: str, display: str, start: float, data: dict = None, error_code: str = None, hints: list = None) -> dict:
    return {
        "meta": {
            "protocol_version": "2024-11-05",
            "skill_id": "calculator",
            "skill_version": "2.0.0",
            "status": status,
            "error_code": error_code,
            "execution_time_ms": int((time.time() - start) * 1000)
        },
        "data": data,
        "display": display,
        "hints": hints or []
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011)