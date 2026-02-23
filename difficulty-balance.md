
#### 难度平衡：`difficulty-balance.md`

```markdown
---
name: difficulty-balance
version: 1.0.0
description: "动态难度调整技能，基于玩家数据自动调整游戏难度"
---

## 功能说明
实现简单可实现的动态难度调整（DDA），把关卡体验控制在目标通关率区间内。

## 输入参数
- 玩家表现数据：
  - 通关率
  - 平均失败次数
  - 平均通关时长
- 当前难度系数：默认 1.0
- 目标难度区间：例如通关率 40%–60%

## 算法逻辑（示例）

```python
# 动态难度调整算法示例（伪代码）

def adjust_difficulty(clear_rate: float, coeff: float) -> float:
    if clear_rate < 0.4:
        # 太难，降低难度
        return coeff * 0.8
    elif clear_rate > 0.7:
        # 太简单，提高难度
        return coeff * 1.2
    else:
        # 在目标区间，保持不变
        return coeff

输出格式
新的难度系数（float）
一段文字说明本次调整的原因
推荐调整项列表（敌人生命/攻击、掉落、奖励等）
示例表：

项目	原值	新值	说明
难度系数	1.0	0.8	通关率过低
敌人攻击系数	1.0	0.9	降低伤害 10%
掉落回复道具	10%	20%	提高恢复资源频率
使用示例
当前第二关通关率只有 30%，请使用 difficulty-balance 技能帮我给出一套难度调整方案，并用伪代码表示更新逻辑。