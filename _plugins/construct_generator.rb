require 'json'

module Jekyll
  class ConstructPageGenerator < Generator
    safe true
    priority :normal

    CAP = 300          # 허브 페이지당 서버사이드 렌더링 상한
    TRADE_MIN = 3      # 시군구×업종 허브 최소 업체 수
    NEAR_COUNT = 6

    def generate(site)
      shard_files = Dir.glob(File.join(site.source, '_rawdata', 'con_*.json')).sort
      n_company = n_sg = n_dong = n_trade_sg = 0
      trade_totals = Hash.new { |h, k| h[k] = Hash.new(0) }   # trade => {"do sg" => count}
      trade_sg_slugs = Hash.new { |h, k| h[k] = [] }

      shard_files.each do |path|
        do_short = File.basename(path, '.json').sub('con_', '')
        items = load_json(path)
        next if items.empty?

        by_sg = items.group_by { |i| i['sigungu'] }
        site.pages << DoPage.new(site, do_short, items.size, by_sg)

        by_sg.each do |sg, sg_items|
          sg_slug = sg_items.first['sgSlug']
          by_dong = sg_items.group_by { |i| i['dong'] }

          trade_map = Hash.new { |h, k| h[k] = [] }
          sg_items.each { |c| c['trades'].map { |t| t['n'] }.uniq.each { |tn| trade_map[tn] << c } }
          trade_hubs = trade_map.select { |_, v| v.size >= TRADE_MIN }

          site.pages << SigunguPage.new(site, do_short, sg, sg_slug, sg_items.size, by_dong, trade_hubs)
          n_sg += 1

          by_dong.each do |dong, list|
            site.pages << DongPage.new(site, do_short, sg, sg_slug, dong, list)
            n_dong += 1

            sorted = list.sort_by { |i| [i['firstDate'].to_s, i['slug']] }
            sorted.each_with_index do |c, idx|
              nb = (1..[NEAR_COUNT, sorted.size - 1].min).map { |k| sorted[(idx + k) % sorted.size] }
                   .map { |x| { 'slug' => x['slug'], 'name' => x['companyName'] } }
              site.pages << CompanyPage.new(site, c, nb)
              n_company += 1
            end
          end

          trade_hubs.each do |tn, list|
            site.pages << TradeSigunguPage.new(site, tn, do_short, sg, sg_slug, list)
            trade_totals[tn]["#{do_short}|#{sg}|#{sg_slug}"] = list.size
            n_trade_sg += 1
          end
        end
      end

      trade_list = trade_totals.map { |tn, h| { 'name' => tn, 'count' => h.values.sum } }.sort_by { |h| -h['count'] }
      site.pages << TradeIndexPage.new(site, trade_list)
      trade_totals.each do |tn, h|
        entries = h.map { |k, v| d, s, ss = k.split('|'); { 'do' => d, 'sigungu' => s, 'sgSlug' => ss, 'count' => v } }
                   .sort_by { |e| [-e['count']] }
        site.pages << TradePage.new(site, tn, entries)
      end

      Jekyll.logger.info 'ConstructGenerator:', "시군구 #{n_sg} / 동 #{n_dong} / 업종×시군구 #{n_trade_sg} / 업종 #{trade_list.size} / 업체 #{n_company}"
    end

    private

    def load_json(path)
      JSON.parse(File.read(path, encoding: 'utf-8'))
    rescue => e
      Jekyll.logger.warn 'ConstructGenerator:', "#{path} 로드 실패: #{e.message}"
      []
    end
  end

  class DoPage < Page
    def initialize(site, do_short, total, by_sg)
      @site = site; @base = site.source; @dir = "region/#{do_short}"; @name = 'index.html'
      list = by_sg.map { |sg, l| { 'name' => sg, 'slug' => l.first['sgSlug'], 'count' => l.size } }.sort_by { |h| -h['count'] }
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'do.html')
      data['layout'] = 'do'
      data['doShort'] = do_short
      data['totalCount'] = total
      data['sigunguList'] = list
      data['title'] = "#{do_short} 건설업체 #{total}곳 - 시군구별 건설업 등록 정보"
      data['description'] = "#{do_short}의 건설업 등록 공시 업체 #{total}곳을 시군구·동·업종별로 확인하세요. 등록업종과 업종등록번호, 대표자, 공시 이력을 공공데이터로 안내합니다."[0, 155]
    end
  end

  class SigunguPage < Page
    def initialize(site, do_short, sg, sg_slug, total, by_dong, trade_hubs)
      @site = site; @base = site.source; @dir = "region/#{do_short}/#{sg_slug}"; @name = 'index.html'
      dongs = by_dong.map { |dg, l| { 'name' => dg, 'count' => l.size } }
                     .sort_by { |h| h['name'] == '기타' ? [1, 0] : [0, -h['count']] }
      trades = trade_hubs.map { |tn, l| { 'name' => tn, 'count' => l.size } }.sort_by { |h| -h['count'] }
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'sigungu.html')
      data['layout'] = 'sigungu'
      data['doShort'] = do_short
      data['sigungu'] = sg
      data['sgSlug'] = sg_slug
      data['totalCount'] = total
      data['dongList'] = dongs
      data['tradeList'] = trades
      data['title'] = "#{do_short} #{sg} 건설업체 #{total}곳 - 동별·업종별 건설업 등록 정보"
      data['description'] = "#{do_short} #{sg}의 건설업체 #{total}곳을 동·읍·면과 등록업종별로 찾아보세요. 업종등록번호와 공시 이력을 확인할 수 있습니다."[0, 155]
    end
  end

  class DongPage < Page
    def initialize(site, do_short, sg, sg_slug, dong, list)
      @site = site; @base = site.source; @dir = "region/#{do_short}/#{sg_slug}/#{dong}"; @name = 'index.html'
      capped = list.sort_by { |i| i['companyName'] }.first(ConstructPageGenerator::CAP)
      label = dong == '기타' ? '기타 지역' : dong
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'dong.html')
      data['layout'] = 'dong'
      data['doShort'] = do_short
      data['sigungu'] = sg
      data['sgSlug'] = sg_slug
      data['dong'] = dong
      data['dongLabel'] = label
      data['totalCount'] = list.size
      data['truncated'] = list.size > ConstructPageGenerator::CAP
      data['items'] = capped
      data['title'] = "#{sg} #{label} 건설업체 #{list.size}곳 (#{do_short})"
      data['description'] = "#{do_short} #{sg} #{label}에 등록된 건설업체 #{list.size}곳 목록. 업체명·등록업종·업종등록번호·대표자를 확인하고 계약 전 등록 여부를 점검하세요."[0, 155]
    end
  end

  class TradeSigunguPage < Page
    def initialize(site, trade, do_short, sg, sg_slug, list)
      @site = site; @base = site.source; @dir = "trade/#{trade}/#{do_short}/#{sg_slug}"; @name = 'index.html'
      capped = list.sort_by { |i| i['companyName'] }.first(ConstructPageGenerator::CAP)
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'trade_sg.html')
      data['layout'] = 'trade_sg'
      data['trade'] = trade
      data['doShort'] = do_short
      data['sigungu'] = sg
      data['sgSlug'] = sg_slug
      data['totalCount'] = list.size
      data['truncated'] = list.size > ConstructPageGenerator::CAP
      data['items'] = capped
      data['title'] = "#{sg} #{trade} 등록 건설업체 #{list.size}곳 (#{do_short})"
      data['description'] = "#{do_short} #{sg}에서 #{trade}으로 등록된 건설업체 #{list.size}곳의 업체명·업종등록번호·대표자 정보를 확인하세요."[0, 155]
    end
  end

  class TradePage < Page
    def initialize(site, trade, entries)
      @site = site; @base = site.source; @dir = "trade/#{trade}"; @name = 'index.html'
      total = entries.sum { |e| e['count'] }
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'trade.html')
      data['layout'] = 'trade'
      data['trade'] = trade
      data['totalCount'] = total
      data['entries'] = entries
      data['title'] = "#{trade} 등록 건설업체 - 지역별 목록"
      data['description'] = "#{trade}으로 등록된 건설업체를 시도·시군구별로 찾아보세요. 업종등록번호와 대표자 정보를 공공데이터로 확인합니다."[0, 155]
    end
  end

  class TradeIndexPage < Page
    def initialize(site, trade_list)
      @site = site; @base = site.source; @dir = 'trade'; @name = 'index.html'
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'trade_index.html')
      data['layout'] = 'trade_index'
      data['tradeList'] = trade_list
      data['title'] = '건설업 등록업종별 업체 찾기'
      data['description'] = '실내건축공사업, 토목공사업, 철근콘크리트공사업 등 건설업 등록업종별로 업체를 찾아보세요.'
    end
  end

  class CompanyPage < Page
    def initialize(site, c, near)
      @site = site; @base = site.source; @dir = "company/#{c['slug']}"; @name = 'index.html'
      process(@name)
      read_yaml(File.join(@base, '_layouts'), 'company.html')
      data.merge!(c)
      data['layout'] = 'company'
      data['near'] = near
      data['dongLabel'] = c['dong'] == '기타' ? '기타 지역' : c['dong']
      first_year = c['firstDate'].to_s[0, 4].to_i
      data['sinceYears'] = first_year > 1990 ? (2026 - first_year) : nil
      trade_names = c['trades'].map { |t| t['n'] }
      data['tradeSummary'] = trade_names.first(2).join('·') + (trade_names.size > 2 ? " 외 #{trade_names.size - 2}개" : '')
      dong_part = c['dong'] == '기타' ? '' : " #{c['dong']}"
      data['title'] = "#{c['companyName']} (#{c['doShort']} #{c['sigungu']}#{dong_part}) #{data['tradeSummary']} 등록 정보"
      data['description'] = "#{c['doShort']} #{c['sigungu']}#{dong_part} #{c['companyName']}의 건설업 등록업종(#{data['tradeSummary']})과 업종등록번호, 대표자, 공시 이력을 확인하세요."[0, 155]
    end
  end

  # 사이트맵: 5만 건 한도 때문에 40,000건씩 분할 + 인덱스
  class ConstructSitemapGenerator < Generator
    safe true
    priority :lowest
    CHUNK = 40_000

    def generate(site)
      urls = site.pages.reject { |p| p.url.to_s.end_with?('.json', '.xml', '.txt', '.js', '.css') || p.url.to_s == '/404.html' || p.data['sitemap'] == false }
                       .map { |p| p.url }.uniq
      base = site.config['url'].to_s
      chunks = urls.each_slice(CHUNK).to_a
      chunks.each_with_index do |c, idx|
        body = +"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
        c.each { |u| body << "  <url><loc>#{base}#{u}</loc></url>\n" }
        body << "</urlset>\n"
        site.pages << raw_page(site, "sitemap-#{idx + 1}.xml", body)
      end
      index = +"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<sitemapindex xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
      chunks.each_index { |idx| index << "  <sitemap><loc>#{base}/sitemap-#{idx + 1}.xml</loc></sitemap>\n" }
      index << "</sitemapindex>\n"
      site.pages << raw_page(site, 'sitemap.xml', index)
      Jekyll.logger.info 'ConstructSitemap:', "#{urls.size}개 URL → #{chunks.size}개 사이트맵"
    end

    private

    def raw_page(site, name, content)
      pg = PageWithoutAFile.new(site, site.source, '', name)
      pg.content = content
      pg.data['layout'] = nil
      pg.data['sitemap'] = false
      pg
    end
  end
end
