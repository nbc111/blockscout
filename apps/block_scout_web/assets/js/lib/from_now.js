import $ from 'jquery'
import moment from 'moment'

moment.relativeTimeThreshold('M', 12)
moment.relativeTimeThreshold('d', 30)
moment.relativeTimeThreshold('h', 24)
moment.relativeTimeThreshold('m', 60)
moment.relativeTimeThreshold('s', 60)
moment.relativeTimeThreshold('ss', 1)

export function updateAllAges ($container = $(document)) {
  $container.find('[data-from-now]').each((i, el) => tryUpdateAge(el))
  return $container
}
function tryUpdateAge (el) {
  if (!el.dataset.fromNow) return

  // 修复：使用 moment.utc() 确保时间戳被解析为UTC时间
  // 因为数据库存储的是 timestamp without time zone，应该按UTC处理
  const timestamp = moment.utc(el.dataset.fromNow)
  if (timestamp.isValid()) updateAge(el, timestamp)
}
function updateAge (el, timestamp) {
  // 计算相对时间（使用UTC时间）
  let fromNow = timestamp.fromNow()
  // show the exact time only for transaction details page. Otherwise, short entry
  const elInTile = el.hasAttribute('in-tile')
  if ((window.location.pathname.includes('/tx/') || window.location.pathname.includes('/block/') || window.location.pathname.includes('/blocks/')) && !elInTile) {
    // 修复：转换为本地时区并正确格式化
    const localTime = timestamp.local()
    const offsetStr = localTime.format('Z') // 自动获取时区偏移，如 +08:00
    // 修复：使用正确的日期格式，使用方括号避免moment.js解析为时区指令
    // 格式：Dec 04 2025 12:14:48 PM (UTC+08:00)
    const formatDate = `MMM DD YYYY hh:mm:ss A [(UTC${offsetStr})]`
    fromNow = `${fromNow} | ${localTime.format(formatDate)}`
  }
  if (fromNow !== el.innerHTML) el.innerHTML = fromNow
}
updateAllAges()

setInterval(updateAllAges, 1000)
