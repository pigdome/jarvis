" normal
syntax on
colorscheme desert

set tabstop=4 shiftwidth=4 expandtab
set mouse-=a

" for perl template toolkit
au BufReadPost *.tt set syntax=html
au BufReadPost *.inc set syntax=html

" for sshconfig
au BufReadPost *.ssh/config.d/* set syntax=sshconfig

" for Makefile
autocmd FileType make set noexpandtab shiftwidth=4 softtabstop=0
