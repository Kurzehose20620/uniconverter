-- uniconverter's pandoc filter. pandoc runs with --sandbox and so reads nothing but
-- the input file. This filter
--   * puts images that sit next to the document into pandoc's media bag, so they
--     are still embedded (UNICONVERTER_BASE = the document's folder),
--   * replaces remote images (http:, https:, //...) by their description – they are
--     never fetched,
--   * drops raw Typst code when typesetting a PDF (it could import online packages),
--   * names untitled e-books and web pages after the file instead of "UNTITLED".

local base = os.getenv("UNICONVERTER_BASE") or "."

local function is_remote(src)
  return src:match("^%a[%w+.-]*:") ~= nil or src:match("^//") ~= nil
end

local function unescape(s)
  return (s:gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end))
end

function Image(img)
  local src = img.src
  if src:match("^data:") then
    return nil
  end
  if is_remote(src) then
    return pandoc.Span(img.caption)
  end
  if pandoc.mediabag.lookup(src) == nil then
    local path = src:sub(1, 1) == "/" and src or (base .. "/" .. src)
    local f = io.open(unescape(path), "rb")
    if f then
      local data = f:read("a")
      f:close()
      pandoc.mediabag.insert(src, nil, data)
    end
  end
  return nil
end

function RawBlock(el)
  if FORMAT == "typst" and el.format == "typst" then
    return {}
  end
end

function RawInline(el)
  if FORMAT == "typst" and el.format == "typst" then
    return {}
  end
end

function Meta(m)
  if m.title == nil and (FORMAT:match("epub") or FORMAT:match("html")) then
    local f = PANDOC_STATE.input_files[1] or "Document"
    local name = (f:match("([^/]+)$") or f):gsub("%.[^.]*$", "")
    if FORMAT:match("epub") then
      m.title = name
    else
      m.pagetitle = name
    end
    return m
  end
end
