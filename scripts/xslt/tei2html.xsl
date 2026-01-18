<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:tei="http://www.tei-c.org/ns/1.0"
                xmlns:xml="http://www.w3.org/XML/1998/namespace"
                exclude-result-prefixes="tei xml">
    
    <xsl:output method="html" encoding="UTF-8" indent="yes"/>
    
    <xsl:key name="handById" match="tei:handNote" use="@xml:id"/>
    
    <xsl:param name="sourceFile" select="''"/>
    
    <xsl:template match="/">
        <html lang="pt-BR">
            <head>
                <meta charset="utf-8"/>
                <meta name="viewport" content="width=device-width, initial-scale=1"/>
                <title>
                    <xsl:value-of select="normalize-space(//tei:teiHeader//tei:titleStmt/tei:title[1])"/>
                </title>
                <link rel="stylesheet" href="../../css/styles.css"/>
            </head>
            
            <body>
                <xsl:attribute name="class">vd-viewer</xsl:attribute>
                
                <xsl:if test="string-length(normalize-space($sourceFile)) &gt; 0">
                    <xsl:attribute name="data-file">
                        <xsl:value-of select="normalize-space($sourceFile)"/>
                    </xsl:attribute>
                </xsl:if>
                
                <main class="main-content">
                    <div class="content-wrapper">
                        <div class="left-column">
                            <div class="transcription-box">
                                
                                <div id="letter-info" style="margin-bottom:0.75rem;">
                                    <div class="letter-title">
                                        <xsl:value-of select="normalize-space(//tei:teiHeader//tei:titleStmt/tei:title[1])"/>
                                    </div>
                                    <div class="letter-date">
                                        <xsl:value-of select="string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type='sent'][1]/tei:date[1]/@when))"/>
                                    </div>
                                </div>
                                
                                <div class="tei-body">
                                    <xsl:apply-templates select="//tei:text/tei:body/tei:div[1]"/>
                                </div>
                                
                            </div>
                        </div>
                    </div>
                </main>
            </body>
        </html>
    </xsl:template>
    
    <xsl:template name="hand-label">
        <xsl:param name="ref"/>
        
        <xsl:variable name="id">
            <xsl:choose>
                <xsl:when test="starts-with($ref,'#')">
                    <xsl:value-of select="substring($ref,2)"/>
                </xsl:when>
                <xsl:otherwise>
                    <xsl:value-of select="$ref"/>
                </xsl:otherwise>
            </xsl:choose>
        </xsl:variable>
        
        <xsl:variable name="hn" select="key('handById',$id)[1]"/>
        
        <xsl:choose>
            <xsl:when test="$hn and normalize-space(string($hn/tei:persName[1])) != ''">
                <xsl:value-of select="normalize-space(string($hn/tei:persName[1]))"/>
            </xsl:when>
            <xsl:otherwise>
                <xsl:value-of select="$id"/>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>
    
    <xsl:template name="note-hand-prefix">
        <xsl:if test="@hand">
            <div class="tei-handshift">
                <xsl:text>Letra de </xsl:text>
                <xsl:call-template name="hand-label">
                    <xsl:with-param name="ref" select="@hand"/>
                </xsl:call-template>
            </div>
        </xsl:if>
    </xsl:template>
    
    <xsl:template match="tei:div">
        <div class="tei-div">
            <xsl:apply-templates/>
        </div>
        <div class="tei-spacer"></div>
    </xsl:template>
    
    <xsl:template match="tei:opener|tei:closer|tei:postscript|tei:dateline|tei:salute|tei:signed|tei:addressee">
        <div>
            <xsl:attribute name="class">
                <xsl:text>tei-</xsl:text>
                <xsl:value-of select="local-name()"/>
            </xsl:attribute>
            <xsl:apply-templates/>
        </div>
    </xsl:template>
    
    <xsl:template match="tei:p">
        <p><xsl:apply-templates/></p>
    </xsl:template>
    
    <xsl:template match="tei:head">
        <h3><xsl:apply-templates/></h3>
    </xsl:template>
    
    <xsl:template match="tei:lg">
        <div class="tei-lg">
            <xsl:apply-templates/>
        </div>
    </xsl:template>
    
    <xsl:template match="tei:l">
        <div class="tei-l">
            <xsl:apply-templates/>
        </div>
    </xsl:template>
    
    <xsl:template match="tei:list">
        <ul class="tei-list">
            <xsl:apply-templates/>
        </ul>
    </xsl:template>
    
    <xsl:template match="tei:item">
        <li><xsl:apply-templates/></li>
    </xsl:template>
    
    <xsl:template match="tei:table">
        <table class="tei-table">
            <tbody>
                <xsl:apply-templates/>
            </tbody>
        </table>
    </xsl:template>
    
    <xsl:template match="tei:row">
        <tr><xsl:apply-templates/></tr>
    </xsl:template>
    
    <xsl:template match="tei:cell">
        <td><xsl:apply-templates/></td>
    </xsl:template>
    
    <xsl:template match="tei:note[@type='endorsement']">
        <div class="tei-endorsement">
            <xsl:call-template name="note-hand-prefix"/>
            <xsl:apply-templates/>
        </div>
    </xsl:template>
    
    <xsl:template match="tei:note[@type='hand']">
        <span class="tei-note-hand">
            <xsl:call-template name="note-hand-prefix"/>
            <xsl:apply-templates/>
        </span>
    </xsl:template>
    
    <xsl:template match="tei:note[not(@type='endorsement') and not(@type='hand')]">
        <div class="tei-note">
            <xsl:call-template name="note-hand-prefix"/>
            <xsl:apply-templates/>
        </div>
    </xsl:template>
    
    <xsl:template match="tei:handShift">
        <div class="tei-handshift">
            <xsl:text>Letra de </xsl:text>
            <xsl:call-template name="hand-label">
                <xsl:with-param name="ref" select="@new"/>
            </xsl:call-template>
        </div>
    </xsl:template>
    
    <xsl:template match="tei:choice">
        <xsl:choose>
            <xsl:when test="tei:expan">
                <xsl:apply-templates select="tei:expan/node()"/>
            </xsl:when>
            <xsl:when test="tei:abbr">
                <xsl:apply-templates select="tei:abbr/node()"/>
            </xsl:when>
            <xsl:otherwise>
                <xsl:apply-templates/>
            </xsl:otherwise>
        </xsl:choose>
    </xsl:template>
    
    <xsl:template match="tei:expan|tei:abbr">
        <xsl:apply-templates/>
    </xsl:template>
    
    <xsl:template match="tei:pb">
        <!-- Hide page/surface markers in reading view -->
    </xsl:template>
    
    <xsl:template match="tei:seg[@type='folio']">
        <!-- Hide folio seg in reading view -->
        <xsl:apply-templates/>
    </xsl:template>
    
    <xsl:template match="tei:persName|tei:placeName|tei:orgName">
        <span class="annotated">
            <xsl:if test="@ref">
                <xsl:attribute name="data-ref">
                    <xsl:value-of select="@ref"/>
                </xsl:attribute>
            </xsl:if>
            <xsl:apply-templates/>
        </span>
    </xsl:template>
    
    <xsl:template match="tei:date">
        <span class="annotated">
            <xsl:if test="@when">
                <xsl:attribute name="data-when">
                    <xsl:value-of select="@when"/>
                </xsl:attribute>
            </xsl:if>
            <xsl:apply-templates/>
        </span>
    </xsl:template>
    
    <xsl:template match="tei:lb">
        <br/>
    </xsl:template>
    
    <!-- ===== Whitespace handling (fix for choice+choice collapsing) ===== -->
    <xsl:template match="text()[normalize-space(.)='']">
        <xsl:choose>
            <!-- inside text-flow containers: keep ONE space only when it is between nodes -->
            <xsl:when test="parent::tei:p or parent::tei:head or parent::tei:l or parent::tei:note or parent::tei:ab or parent::tei:seg">
                <xsl:if test="preceding-sibling::node() and following-sibling::node()">
                    <xsl:text> </xsl:text>
                </xsl:if>
            </xsl:when>
            <!-- otherwise: drop indentation whitespace -->
            <xsl:otherwise/>
        </xsl:choose>
    </xsl:template>
    
    <xsl:template match="text()">
        <xsl:value-of select="."/>
    </xsl:template>
    
</xsl:stylesheet>