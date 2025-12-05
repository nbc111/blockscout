defmodule BlockScoutWeb.CSPHeader do
  @moduledoc """
  Plug to set content-security-policy with websocket endpoints
  """

  alias Phoenix.Controller
  alias Plug.Conn

  def init(opts), do: opts

  def call(conn, _opts) do
    config = Application.get_env(:block_scout_web, __MODULE__)
    google_url = "https://www.google.com"
    czilladx_url = "https://request-global.czilladx.com"
    coinzillatag_url = "https://coinzillatag.com"
    trustwallet_url = "https://raw.githubusercontent.com/trustwallet/assets/"
    walletconnect_urls = "wss://*.bridge.walletconnect.org https://registry.walletconnect.org/data/wallets.json"
    json_rpc_url = sanitize_json_rpc_url(Application.get_env(:block_scout_web, :json_rpc))
    json_rpc_src = if json_rpc_url == "", do: "", else: " #{json_rpc_url}"

    Controller.put_secure_browser_headers(conn, %{
      "content-security-policy" => "\
        connect-src 'self'#{json_rpc_src} #{config[:mixpanel_url]} #{config[:amplitude_url]} #{websocket_endpoints(conn)} #{czilladx_url} #{trustwallet_url} #{walletconnect_urls};\
        default-src 'self';\
        script-src 'self' 'unsafe-inline' 'unsafe-eval' #{coinzillatag_url} #{google_url} https://www.gstatic.com;\
        style-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com;\
        img-src 'self' * data:;\
        media-src 'self' * data:;\
        font-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.gstatic.com data:;\
        frame-src 'self' 'unsafe-inline' 'unsafe-eval' #{czilladx_url} #{google_url};\
      "
    })
  end

  # 清理和验证 JSON RPC URL，移除无效的前缀（如 *.https://）
  defp sanitize_json_rpc_url(nil), do: ""
  
  defp sanitize_json_rpc_url(url) when is_binary(url) do
    url
    |> String.trim()
    |> String.replace(~r/^\*\./, "")  # 移除开头的 *. 前缀
    |> String.replace(~r/^\*/, "")    # 移除开头的 * 前缀
    |> case do
      "" -> ""
      cleaned_url -> cleaned_url
    end
  end
  
  defp sanitize_json_rpc_url(_), do: ""

  defp websocket_endpoints(conn) do
    host = Conn.get_req_header(conn, "host")
    "ws://#{host} wss://#{host}"
  end
end
