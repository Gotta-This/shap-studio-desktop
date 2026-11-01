export function homeMessage(now: Date): string {
  const minute = now.getHours() * 60 + now.getMinutes();
  if (minute >= 60 && minute < 420) return "该睡觉了宝宝，明天再加油吧 😘🌙";
  if (
    (minute >= 420 && minute < 540) ||
    (minute >= 690 && minute < 810) ||
    (minute >= 1050 && minute < 1170)
  )
    return "该补充能量了，宝宝记得吃饭呀 🍚❤️";
  if (minute >= 540 && minute < 1080) return "加油宝宝 💪❤️";
  return "辛苦啦宝宝，忙完记得好好休息 😘❤️";
}
