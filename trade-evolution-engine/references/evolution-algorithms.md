# 自进化算法路线

更新日期：2026-04-12

这份说明聚焦一个核心判断：

当前这套账本已经有“交易级闭环样本”，但还没有“盘中逐步状态-动作-奖励轨迹”。

因此，这一版自进化更适合先走：

- contextual bandit / hybrid bandit 排序
- 轨迹签名聚类
- 风险臂抑制

而不是直接跳到完整强化学习策略。

## 一、为什么当前先选 bandit，而不是直接上 RL

当前已稳定记录的数据主要是：

- 计划标签
- 买卖事实
- 市场阶段
- 环境标签
- 情绪 / 失误 / 经验
- 卖出后回顾反馈

对于量化 / 半量化策略，当前还可以先把这类“非纯执行、但不适合写成传统主观选股理由”的信息记进：

- `decision_context_json.strategy_context`

例如：

- 策略条线
- 因子组
- 参数版本
- 启用原因
- 主观覆盖 / 降杠杆 / 暂停某条线

这些数据已经足够支持：

- 在“当前上下文”下匹配历史相似路径
- 给每条路径 / 基因计算成功率、收益、alpha、风险惩罚
- 用 UCB / posterior mean 之类的 bandit 指标做“先复核谁、先规避谁”的排序

但它还不够支持完整 RL，因为我们缺少：

- 盘中逐时状态序列
- 每次动作的精确触发时刻
- 动作之后的连续反馈
- 明确的 action space 与 policy constraint

所以当前最合理的做法是：

1. 先把交易级样本做成 contextual bandit 风格的决策支持
2. 等后续补齐更细粒度轨迹，再升级到 offline RL

## 二、这一版已经落地的算法思路

### 1. 轨迹臂（path arms）

把一笔闭环交易压缩成：

- 逻辑
- 形态
- 市场阶段
- 环境
- 纪律执行特征

只要形成至少两个关键条件，就视作一条“轨迹臂”。

对每条臂统计：

- sample_size
- win_rate
- avg_actual_return_pct
- avg_timing_alpha_pct
- effective_count

再叠加：

- posterior mean
- exploration bonus
- UCB score
- conservative score

用于排序“更值得优先复核的历史路径”。

### 2. 基因臂（gene arms）

把标签、纪律、情绪、失误、回顾反馈都看成基因臂。

正向基因：

- 买点在计划内
- 卖点在计划内
- 有效卖出被确认
- 长期高胜率 / 正收益标签

风险基因：

- 买点偏离计划
- 卖点偏离计划
- 冲动追高
- 急躁 / 慌张 / 害怕
- 卖飞被确认

风险基因除了 posterior / exploration 以外，还会单独计算 `risk_penalty_score`。

### 3. 提醒层

在 `evolution remind` / `evolution portrait` 里：

- 先按上下文标签匹配历史路径
- 再用 bandit 分数排序
- 同时挑出当前最需要压制的风险臂

输出给 OpenClaw 的不是“买卖信号”，而是：

- 哪条历史路径更值得先复核
- 哪个老问题最该先压住
- 哪几个反思问题最值得先问

## 三点五、量化 / 半量化策略的独立轨迹线

当前建议把量化记录拆成两层：

1. 执行事实层：买卖日期、价格、仓位、收益
2. 策略上下文层：策略条线、因子组、参数版本、启用原因、主观覆盖

原因是：

- 代码固化了很多执行逻辑
- 但“今天为什么开这条线 / 为什么换这组因子 / 为什么降权某个策略”仍然属于人的决策
- 这些决策本身也应该形成可复盘、可进化的轨迹

当前实现已经支持把这层上下文记进账本并展示在 Vault。

但独立的量化轨迹排序、策略线风格画像、因子漂移报告，仍然属于下一阶段能力。

## 三、为什么这比直接做强化学习更稳

因为当前系统的目标不是自动执行策略，而是：

- 帮用户复用自己的有效历史
- 帮用户识别反复出现的风险模式
- 在样本仍不够细时，先给出稳健的排序和复核

这和 bandit 的“在有限反馈下做探索 / 利用平衡”更一致。

## 四、未来升级到 offline RL 的前提

当下面这些数据补齐以后，再考虑升级到 offline RL：

- 盘中状态快照（分时、盘口、板块强度、仓位变化）
- 动作序列（加仓、减仓、止盈、止损、撤单）
- 更细粒度 reward 定义
- 明确的风险约束
- 足够长时间、足够多样本的离线轨迹库

到那时可以考虑：

- Decision Transformer 风格的 trajectory policy
- IQL 风格的保守 offline RL
- 加入交易成本 / 回撤 / 风险预算的约束优化

## 五、当前参考的论文与启发

以下论文只是“算法路线参考”，当前实现并不是它们的逐字复现：

1. Lihong Li, Wei Chu, John Langford, Robert E. Schapire, “A Contextual-Bandit Approach to Personalized News Article Recommendation”  
   https://arxiv.org/abs/1003.0146

   启发：
   - 上下文匹配
   - exploration / exploitation 平衡
   - 在日志数据上做离线评估

2. Daniel Golovin et al., “SmartChoices: Augmenting Software with Learned Implementations”  
   https://arxiv.org/abs/2304.13033

   启发：
   - 先把 bandit 作为软件里的“可控增强层”
   - 将上下文、arms、反馈接口做清晰分离
   - 适合把启发式系统逐步升级成 learned ranking layer

3. Lili Chen et al., “Decision Transformer: Reinforcement Learning via Sequence Modeling”  
   https://arxiv.org/abs/2106.01345

   启发：
   - 当轨迹足够丰富时，可以把历史交易轨迹当成序列建模问题
   - 更适合后续补齐盘中序列后的升级路线

4. Ilya Kostrikov, Ashvin Nair, Sergey Levine, “Offline Reinforcement Learning with Implicit Q-Learning”  
   https://arxiv.org/abs/2110.06169

   启发：
   - 先在离线数据里学习，再考虑极少量在线微调
   - 对“不能随便偏离历史分布”的风险更敏感

## 六、给这个框架的结论

现阶段建议：

- 默认用 contextual bandit 做自进化排序层
- 用风险臂做纪律 / 情绪 / 失误抑制
- 把每笔交易继续沉淀成更细粒度轨迹数据

下一阶段再做：

- offline RL
- trajectory transformer
- 更细粒度状态-动作-奖励建模
