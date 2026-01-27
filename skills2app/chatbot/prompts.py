"""
Bilingual Prompts for Spec-Drafting Chatbot

These prompts are META (field-agnostic) - they work for any domain book.
Each prompt has English and Chinese versions, selected via OUTPUT_LANGUAGE in .env.

Design Principles:
1. Guide users who are NOT professional developers
2. Provide options to choose from
3. Confirm understanding before proceeding
4. Use simple, non-technical language
"""

# ============================================================================
# System Prompts
# ============================================================================

SYSTEM_PROMPT = {
    "English": """You are a friendly assistant helping users design applications based on professional knowledge from a book.

Your role:
1. GUIDE the user step by step - they may not be technical experts
2. ALWAYS provide numbered options for the user to choose from
3. CONFIRM understanding before moving to the next step
4. Use SIMPLE language, avoid jargon
5. Be patient and encouraging

You have access to a router that describes the book's structure and available skills:
- Domains: High-level topics from the book
- Skills: Specific capabilities that can be built into an app
- Dependencies: Which skills need other skills to work properly
- Completeness Groups: Skills that work well together

Your goal is to help the user create a "spec" (specification) that describes what app they want to build.

Important rules:
- Never assume the user knows technical terms
- Always offer to explain if something is unclear
- Break complex decisions into smaller, manageable choices
- Summarize and confirm before finalizing""",

    "Chinese": """你是一个友好的助手，帮助用户基于专业书籍中的知识设计应用程序。

你的角色：
1. 一步一步引导用户 - 他们可能不是技术专家
2. 始终提供编号选项供用户选择
3. 在进入下一步之前确认理解
4. 使用简单的语言，避免术语
5. 耐心且鼓励

你可以访问一个路由器，它描述了书籍的结构和可用技能：
- 领域：书中的高级主题
- 技能：可以构建到应用程序中的具体能力
- 依赖关系：哪些技能需要其他技能才能正常工作
- 完整性组：配合良好的技能组合

你的目标是帮助用户创建一个"规格说明"，描述他们想要构建的应用。

重要规则：
- 永远不要假设用户了解技术术语
- 如果有不清楚的地方，始终主动解释
- 将复杂的决定分解成更小、更易管理的选择
- 在最终确定之前总结并确认"""
}

# ============================================================================
# Welcome Message
# ============================================================================

WELCOME_MESSAGE = {
    "English": """Hello! I'm here to help you design an application based on the knowledge in "{book_name}".

I'll guide you through a few simple steps to create your app specification.

{domains_list}

**Quick Start:** Enter 'A' to use all skills from the book (recommended for most users)

Or enter a number to select a specific domain, or describe what you want to do:""",

    "Chinese": """你好！我来帮助你基于《{book_name}》中的知识设计一个应用程序。

我会引导你完成几个简单的步骤来创建你的应用规格说明。

{domains_list}

**快速开始：** 输入 'A' 使用本书的全部技能（推荐大多数用户使用）

或者输入数字选择特定领域，或描述你想做什么："""
}

# ============================================================================
# Domain Selection
# ============================================================================

DOMAIN_SELECTED = {
    "English": """Great choice! You selected: **{domain_name}**

This topic includes the following capabilities:

{skills_list}

What would you like to do next?
1. Select specific capabilities from this list
2. See more details about a capability (enter its number)
3. Go back and choose a different topic
4. Tell me what you want to accomplish, and I'll suggest capabilities

Your choice:""",

    "Chinese": """很好的选择！你选择了：**{domain_name}**

这个主题包含以下功能：

{skills_list}

你接下来想做什么？
1. 从这个列表中选择具体功能
2. 查看某个功能的更多详情（输入它的编号）
3. 返回选择其他主题
4. 告诉我你想要实现什么，我会推荐功能

你的选择："""
}

# ============================================================================
# Skill Details
# ============================================================================

SKILL_DETAILS = {
    "English": """Here are the details for **{skill_name}**:

**What it does:** {description}

**Works well with:** {related_skills}

**Prerequisites:** {prerequisites}

Would you like to:
1. Add this capability to your app
2. Add this AND its related capabilities (recommended for complete functionality)
3. Go back to the list
4. Ask me a question about this capability

Your choice:""",

    "Chinese": """以下是 **{skill_name}** 的详细信息：

**功能说明：** {description}

**配合使用效果更好：** {related_skills}

**前置要求：** {prerequisites}

你想要：
1. 将此功能添加到你的应用
2. 添加此功能及其相关功能（推荐，以获得完整功能）
3. 返回列表
4. 询问关于此功能的问题

你的选择："""
}

# ============================================================================
# Capability Selection
# ============================================================================

SELECT_CAPABILITIES = {
    "English": """Let's select the capabilities for your app.

Currently selected: {selected_list}

Available capabilities in this topic:
{available_list}

What would you like to do?
1. Add a capability (enter its number)
2. Remove a capability from your selection
3. See a recommended combination
4. I'm done selecting, move to the next step

Your choice:""",

    "Chinese": """让我们选择你的应用需要的功能。

当前已选择：{selected_list}

此主题中可用的功能：
{available_list}

你想要做什么？
1. 添加一个功能（输入它的编号）
2. 从你的选择中移除一个功能
3. 查看推荐的组合
4. 我已选择完毕，进入下一步

你的选择："""
}

# ============================================================================
# Completeness Check
# ============================================================================

COMPLETENESS_CHECK = {
    "English": """Let me check if your selection is complete...

You selected: {selected_skills}

{completeness_message}

{recommendation}

Do you want to:
1. Accept the recommendation and add the suggested capabilities
2. Keep my current selection as is
3. Let me explain why these capabilities are recommended

Your choice:""",

    "Chinese": """让我检查你的选择是否完整...

你选择了：{selected_skills}

{completeness_message}

{recommendation}

你想要：
1. 接受推荐，添加建议的功能
2. 保持我当前的选择不变
3. 让我解释为什么推荐这些功能

你的选择："""
}

COMPLETENESS_OK = {
    "English": "Your selection looks complete! All necessary capabilities are included.",
    "Chinese": "你的选择看起来很完整！所有必要的功能都已包含。"
}

COMPLETENESS_MISSING = {
    "English": "I noticed some capabilities might be missing for a complete solution.",
    "Chinese": "我注意到可能缺少一些功能来实现完整的解决方案。"
}

COMPLETENESS_RECOMMENDATION = {
    "English": "I recommend also adding: {missing_skills}\n\nThese work together with your selected capabilities to provide a more complete solution.",
    "Chinese": "我建议还要添加：{missing_skills}\n\n这些与你选择的功能配合使用，可以提供更完整的解决方案。"
}

# ============================================================================
# App Description
# ============================================================================

DESCRIBE_APP = {
    "English": """Now let's describe your application.

Selected capabilities: {selected_skills}

Please answer these questions (or type 'skip' to use defaults):

1. **What is the main goal of your app?**
   (Example: "Help me analyze financial reports" or "Automate compliance checking")

Your answer:""",

    "Chinese": """现在让我们描述你的应用程序。

已选择的功能：{selected_skills}

请回答这些问题（或输入"跳过"使用默认值）：

1. **你的应用的主要目标是什么？**
   （例如："帮助我分析财务报告"或"自动化合规检查"）

你的回答："""
}

DESCRIBE_APP_USERS = {
    "English": """2. **Who will use this app?**
   (Example: "Finance team", "Compliance officers", "Just me")

Your answer:""",

    "Chinese": """2. **谁会使用这个应用？**
   （例如："财务团队"、"合规人员"、"只有我自己"）

你的回答："""
}

DESCRIBE_APP_FREQUENCY = {
    "English": """3. **How often will this app be used?**

1. Daily
2. Weekly
3. Monthly
4. As needed

Your choice:""",

    "Chinese": """3. **这个应用会多久使用一次？**

1. 每天
2. 每周
3. 每月
4. 按需使用

你的选择："""
}

# ============================================================================
# Confirmation
# ============================================================================

CONFIRM_SPEC = {
    "English": """Let me summarize what we've discussed:

**Application Name:** {app_name}
**Main Goal:** {main_goal}
**Target Users:** {target_users}
**Usage Frequency:** {frequency}

**Selected Capabilities:**
{capabilities_summary}

**Execution Order:**
{execution_order}

Is this correct?
1. Yes, create my specification
2. No, I want to make changes
3. Let me add more details

Your choice:""",

    "Chinese": """让我总结一下我们讨论的内容：

**应用名称：** {app_name}
**主要目标：** {main_goal}
**目标用户：** {target_users}
**使用频率：** {frequency}

**已选择的功能：**
{capabilities_summary}

**执行顺序：**
{execution_order}

这样正确吗？
1. 是的，创建我的规格说明
2. 不，我想要修改
3. 让我添加更多细节

你的选择："""
}

# ============================================================================
# Completion
# ============================================================================

SPEC_CREATED = {
    "English": """Your application specification has been created!

The spec has been saved to: {output_path}

**What happens next:**
1. The spec will be used to generate your application code
2. You can review and edit the spec file if needed
3. Run the app generator to create your working application

Would you like to:
1. Start a new specification
2. View the generated spec
3. Exit

Your choice:""",

    "Chinese": """你的应用规格说明已创建！

规格说明已保存到：{output_path}

**接下来会发生什么：**
1. 规格说明将用于生成你的应用程序代码
2. 如果需要，你可以查看和编辑规格说明文件
3. 运行应用生成器来创建你的工作应用

你想要：
1. 开始新的规格说明
2. 查看生成的规格说明
3. 退出

你的选择："""
}

# ============================================================================
# Error & Help Messages
# ============================================================================

INVALID_INPUT = {
    "English": "I didn't understand that. Please enter a number from the options, or type your question.",
    "Chinese": "我没有理解你的输入。请从选项中输入一个数字，或输入你的问题。"
}

HELP_MESSAGE = {
    "English": """**Help**

At any time, you can:
- Enter a number to select an option
- Type 'back' to go to the previous step
- Type 'help' to see this message
- Type 'quit' to exit

I'm here to help you create an application. Just tell me what you need!""",

    "Chinese": """**帮助**

在任何时候，你可以：
- 输入数字来选择一个选项
- 输入"返回"回到上一步
- 输入"帮助"查看此消息
- 输入"退出"退出程序

我在这里帮助你创建应用程序。只需告诉我你需要什么！"""
}

ASK_CLARIFICATION = {
    "English": "I want to make sure I understand correctly. {question}",
    "Chinese": "我想确保我理解正确。{question}"
}

# ============================================================================
# LLM Interaction Prompts
# ============================================================================

INTERPRET_USER_INPUT = {
    "English": """The user said: "{user_input}"

Current context:
- Stage: {stage}
- Available options: {options}
- Selected so far: {selected}

Determine what the user wants:
1. If they selected an option number, return: {{"action": "select", "value": <number>}}
2. If they asked a question, return: {{"action": "question", "question": "<their question>"}}
3. If they described a goal, return: {{"action": "goal", "description": "<their goal>"}}
4. If unclear, return: {{"action": "clarify", "message": "<what to ask>"}}

Return JSON only:""",

    "Chinese": """用户说："{user_input}"

当前上下文：
- 阶段：{stage}
- 可用选项：{options}
- 已选择：{selected}

判断用户想要什么：
1. 如果他们选择了选项编号，返回：{{"action": "select", "value": <数字>}}
2. 如果他们问了问题，返回：{{"action": "question", "question": "<他们的问题>"}}
3. 如果他们描述了目标，返回：{{"action": "goal", "description": "<他们的目标>"}}
4. 如果不清楚，返回：{{"action": "clarify", "message": "<要问什么>"}}

仅返回JSON："""
}

SUGGEST_SKILLS_FOR_GOAL = {
    "English": """The user wants to: "{goal}"

Available skills from the book:
{skills_list}

Based on their goal, suggest the most relevant skills.
Return JSON:
{{
  "suggested_skills": ["skill-id-1", "skill-id-2"],
  "explanation": "Brief explanation of why these skills match their goal"
}}

Return JSON only:""",

    "Chinese": """用户想要："{goal}"

书中可用的技能：
{skills_list}

根据他们的目标，建议最相关的技能。
返回JSON：
{{
  "suggested_skills": ["skill-id-1", "skill-id-2"],
  "explanation": "简要解释为什么这些技能符合他们的目标"
}}

仅返回JSON："""
}

ANSWER_USER_QUESTION = {
    "English": """The user asked: "{question}"

Context:
- Current skill being discussed: {current_skill}
- Available information: {skill_info}

Provide a helpful, simple answer. Avoid technical jargon.
Keep the answer concise (2-3 sentences max).

Answer:""",

    "Chinese": """用户问："{question}"

上下文：
- 当前正在讨论的技能：{current_skill}
- 可用信息：{skill_info}

提供一个有帮助的、简单的回答。避免技术术语。
保持回答简洁（最多2-3句话）。

回答："""
}
