# Maintainer: Michal Krenek (Mikos) <m.krenek@gmail.com>
pkgname=hangupsbot
pkgver=0.1
pkgrel=1
pkgdesc="Bot for Google Hangouts"
arch=('any')
url="https://github.com/xmikos/hangupsbot"
license=('GPL3')
depends=('python-hangups' 'python-tornado' 'python-appdirs')
source=(https://github.com/xmikos/hangupsbot/archive/v$pkgver.tar.gz)

build() {
  cd "$srcdir/$pkgname-$pkgver"
  python setup.py build
}

package() {
  cd "$srcdir/$pkgname-$pkgver"
  python setup.py install --root="$pkgdir"
}

# vim:set ts=2 sw=2 et:
