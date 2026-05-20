export class MintryMandateExceeded extends Error {
  public readonly task: string;
  public readonly cap: number;
  public readonly spent: number;

  constructor(task: string, cap: number, spent: number) {
    super(
      `🛑 [Mintry Shield] Mandate '${task}' exceeded. Hard Cap: $${cap.toFixed(4)} | Current Attributed Spend: $${spent.toFixed(4)}`
    );
    this.name = 'MintryMandateExceeded';
    this.task = task;
    this.cap = cap;
    this.spent = spent;
  }
}
