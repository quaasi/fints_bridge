require "minitest/test_task"

Minitest::TestTask.create

desc "Run the Python checks of fints_bridge.py"
task "test:python" do
  sh "uv", "run", "--quiet", "--with", "fints>=4,<5", "python", "-I", "test/test_fints_bridge.py"
end

desc "Download the current bank directory from hbci4java"
task "banks:update" do
  require "net/http"
  require_relative "lib/fints_bridge"
  File.write(FintsBridge::Bank::PATH, Net::HTTP.get(URI(FintsBridge::Bank::SOURCE_URL)))
end

task default: %w[test test:python]
