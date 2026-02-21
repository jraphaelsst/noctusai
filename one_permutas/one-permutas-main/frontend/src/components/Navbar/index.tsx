import { useContext, useEffect } from 'react'

import {
  DropDown,
  DropDownItem,
  Item,
  ItemAnimation,
  ItemLink,
  NavButton,
  NavbarContainer,
  NavbarRow
} from './styles'

import AuthContext from '../../context/AuthContext'

type Props = {
  children: JSX.Element
}

const Navbar = ({ children }: Props) => {
  const { logoutUser } = useContext(AuthContext)
  const handleLogout = () => {
    logoutUser()
  }

  // Imoveis DropDown Animation
  useEffect(() => {
    const menuEl = document.getElementById('imoveis-menu')
    const iconEl = document.getElementById('imoveis-icon')
    const dropDownEl = document.getElementById('imoveis-dropdown')

    const handleImoveisHover = () => {
      iconEl?.classList.add('active')
      dropDownEl?.classList.add('active')
    }
    const handleImoveisLeave = () => {
      iconEl?.classList.remove('active')
      dropDownEl?.classList.remove('active')
    }

    menuEl?.addEventListener('mouseover', handleImoveisHover)
    menuEl?.addEventListener('mouseout', handleImoveisLeave)

    return () => {
      menuEl?.removeEventListener('mouseover', handleImoveisHover)
      menuEl?.removeEventListener('mouseout', handleImoveisLeave)
    }
  }, [])

  // Condomínios DropDown Animation
  useEffect(() => {
    const menuEl = document.getElementById('condominios-menu')
    const iconEl = document.getElementById('condominios-icon')
    const dropDownEl = document.getElementById('condominios-dropdown')

    const handleCondominiosHover = () => {
      iconEl?.classList.add('active')
      dropDownEl?.classList.add('active')
    }
    const handleCondominiosLeave = () => {
      iconEl?.classList.remove('active')
      dropDownEl?.classList.remove('active')
    }

    menuEl?.addEventListener('mouseover', handleCondominiosHover)
    menuEl?.addEventListener('mouseout', handleCondominiosLeave)

    return () => {
      menuEl?.removeEventListener('mouseover', handleCondominiosHover)
      menuEl?.removeEventListener('mouseout', handleCondominiosLeave)
    }
  }, [])

  // Permutas DropDown Animation
  useEffect(() => {
    const menuEl = document.getElementById('permutas-menu')
    const iconEl = document.getElementById('permutas-icon')
    const dropDownEl = document.getElementById('permutas-dropdown')

    const handlePermutasHover = () => {
      iconEl?.classList.add('active')
      dropDownEl?.classList.add('active')
    }
    const handlePermutasLeave = () => {
      iconEl?.classList.remove('active')
      dropDownEl?.classList.remove('active')
    }

    menuEl?.addEventListener('mouseover', handlePermutasHover)
    menuEl?.addEventListener('mouseout', handlePermutasLeave)

    return () => {
      menuEl?.removeEventListener('mouseover', handlePermutasHover)
      menuEl?.removeEventListener('mouseout', handlePermutasLeave)
    }
  }, [])

  // Clientes DropDown Animation
  useEffect(() => {
    const menuEl = document.getElementById('clientes-menu')
    const iconEl = document.getElementById('clientes-icon')
    const dropDownEl = document.getElementById('clientes-dropdown')

    const handleClientesHover = () => {
      iconEl?.classList.add('active')
      dropDownEl?.classList.add('active')
    }
    const handleClientesLeave = () => {
      iconEl?.classList.remove('active')
      dropDownEl?.classList.remove('active')
    }

    menuEl?.addEventListener('mouseover', handleClientesHover)
    menuEl?.addEventListener('mouseout', handleClientesLeave)

    return () => {
      menuEl?.removeEventListener('mouseover', handleClientesHover)
      menuEl?.removeEventListener('mouseout', handleClientesLeave)
    }
  }, [])

  return (
    <>
      <NavbarContainer>
        <NavbarRow>
          <Item>
            <ItemLink to="/home">
              <ItemAnimation>Home</ItemAnimation>
            </ItemLink>
          </Item>
          <Item id="condominios-menu">
            <NavButton>
              <ItemLink to="/condominios">
                <span>Condomínios</span>
              </ItemLink>
              <div id="condominios-icon" className="">
                <i className="fa-solid fa-arrow-down-long fa-xs"></i>
              </div>
              <DropDown id="condominios-dropdown" className="">
                <DropDownItem>
                  <ItemLink to="/condominios/meus">Meus</ItemLink>
                </DropDownItem>
                <DropDownItem>
                  <ItemLink to="/condominios/novo">Novo</ItemLink>
                </DropDownItem>
              </DropDown>
            </NavButton>
          </Item>
          <Item id="imoveis-menu">
            <NavButton>
              <ItemLink to="/imoveis">
                <span>Imóveis</span>
              </ItemLink>
              <div id="imoveis-icon" className="">
                <i className="fa-solid fa-arrow-down-long fa-xs"></i>
              </div>
              <DropDown id="imoveis-dropdown" className="">
                <DropDownItem>
                  <ItemLink to="/imoveis/meus">Meus</ItemLink>
                </DropDownItem>
                <DropDownItem>
                  <ItemLink to="/imoveis/novo">Novo</ItemLink>
                </DropDownItem>
              </DropDown>
            </NavButton>
          </Item>
          <Item id="permutas-menu">
            <NavButton>
              <ItemLink to="/permutas">
                <span>Permutas</span>
              </ItemLink>
              <div id="permutas-icon" className="">
                <i className="fa-solid fa-arrow-down-long fa-xs"></i>
              </div>
              <DropDown id="permutas-dropdown" className="">
                <DropDownItem>
                  <ItemLink to="/permutas/minhas">Minhas</ItemLink>
                </DropDownItem>
                <DropDownItem>
                  <ItemLink to="/permutas/nova">Nova</ItemLink>
                </DropDownItem>
              </DropDown>
            </NavButton>
          </Item>
          <Item id="clientes-menu">
            <NavButton>
              <ItemLink to="/clientes">
                <span>Clientes</span>
              </ItemLink>
              <div id="clientes-icon" className="">
                <i className="fa-solid fa-arrow-down-long fa-xs"></i>
              </div>
              <DropDown id="clientes-dropdown" className="">
                <DropDownItem>
                  <ItemLink to="/clientes/meus">Meus</ItemLink>
                </DropDownItem>
                <DropDownItem>
                  <ItemLink to="/clientes/novo">Novo</ItemLink>
                </DropDownItem>
              </DropDown>
            </NavButton>
          </Item>
          <Item>
            <NavButton onClick={handleLogout}>
              <ItemAnimation>Logout</ItemAnimation>
            </NavButton>
          </Item>
        </NavbarRow>
      </NavbarContainer>
      {children}
    </>
  )
}

export default Navbar
