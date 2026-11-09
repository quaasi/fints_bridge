require_relative "lib/fints_bridge/version"

Gem::Specification.new do |spec|
  spec.name = "fints_bridge"
  spec.version = FintsBridge::VERSION
  spec.authors = [ "Michael Quaas" ]
  spec.email = [ "michael@qua.as" ]
  spec.summary = "FinTS online banking for Ruby via python-fints, plus a directory of German banks"
  spec.license = "MIT"
  spec.required_ruby_version = ">= 3.3"
  spec.files = Dir["lib/**/*", "data/*", "README.md", "LICENSE"]
  spec.add_dependency "bigdecimal"
end
