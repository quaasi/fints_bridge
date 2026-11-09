class FintsBridge
  # A German bank from data/blz.properties (hbci4java's bank directory, LGPL-2.1): every bank code (BLZ)
  # with name, city, BIC and, where the bank offers it, the FinTS PIN/TAN server URL.
  class Bank < Data.define(:blz, :name, :city, :bic, :fints_url)
    PATH = File.expand_path("../../data/blz.properties", __dir__)
    SOURCE_URL = "https://raw.githubusercontent.com/hbci4j/hbci4java/master/src/main/resources/blz.properties"

    # Finds the bank by BLZ ("12030000"), German IBAN ("DE02 1203 0000 ...") or BIC ("BYLADEM1001" or "BYLADEM1").
    # Several BLZs can share a BIC; then the first one with a FinTS URL wins. Returns nil if unknown.
    def self.find(code)
      code = code.to_s.delete(" ").upcase
      code = code[4, 8] if code.match?(/\ADE\d{20}\z/)
      if code.match?(/\A\d{8}\z/)
        all[code]
      elsif code.match?(/\A[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?\z/)
        code += "XXX" if code.size == 8
        matches = all.each_value.select { |bank| bank.bic == code }
        matches.find(&:fints_url) || matches.first
      end
    end

    def self.all
      @all ||= File.foreach(PATH, chomp: true, encoding: "UTF-8").to_h do |line|
        blz, fields = line.split("=", 2)
        name, city, bic, _check, _rdh_host, fints_url = fields.split("|")
        [ blz, new(blz: blz, name: name, city: city, bic: bic.strip.then { _1 unless _1.empty? }, fints_url: fints_url.then { _1 unless _1.to_s.empty? }) ]
      end.freeze
    end
  end
end
