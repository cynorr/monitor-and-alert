// 所有日图与盘中图共用默认间距；单位为 px，可直接修改。
// 2 px 在当前 1280 px 窗口的 Scan 日图中约显示 12 个月。
export const BAR_SPACING = 5;
// Daily：最近已完成日 K 收盘中位数；锚点距底部 2/3。
export const DAILY_ANCHOR_BARS = 5;
export const DAILY_ANCHOR_POSITION = 2 / 3;
// 相对锚点每变化 1%，纵向占几个 K 线间距；横纵缩放共用此比例。
export const DAILY_PERCENT_BAR_SPACING = 1;
// 成交量占总绘图区的比例；0.28 表示成交量 28%、主图 72%。
export const VOLUME_PANE_RATIO = 0.28;
// 修改本文件后，在项目根运行 npm run build --prefix ui。
