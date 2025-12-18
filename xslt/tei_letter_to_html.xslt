<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet
    version="2.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:tei="http://www.tei-c.org/ns/1.0"
    exclude-result-prefixes="tei">
    
    <xsl:output method="html" encoding="UTF-8" indent="yes"/>
    
    <!-- Root -->
    <xsl:template match="/">
        <html lang="en">
            <head>
                <meta charset="UTF-8"/>
                <title>
                    <xsl:value-of select="//tei:titleStmt/tei:title"/>
                </title>
                <link rel="stylesheet" href="../assets/css/styles.css"/>
            </head>
            <body>
                
                <main class="tei-document">
                    
                    <header class="tei-header">
                        <h1>
                            <xsl:value-of select="//tei:titleStmt/tei:title"/>
                        </h1>
                        
                        <section class="tei-metadata">
                            <xsl:apply-templates select="//tei:correspDesc"/>
                        </section>
                    </header>
                    
                    <article class="tei-body">
                        <xsl:apply-templates select="//tei:div"/>
                    </article>
                    
                </main>
                
            </body>
        </html>
    </xsl:template>
    
    <!-- Correspondence metadata -->
    <xsl:template match="tei:correspDesc">
        <p><strong>Sender:</strong>
            <xsl:value-of select="tei:correspAction[@type='sent']/tei:persName"/>
        </p>
        <p><strong>Receiver:</strong>
            <xsl:value-of select="tei:correspAction[@type='received']/tei:persName"/>
        </p>
        <p><strong>Place:</strong>
            <xsl:value-of select="tei:correspAction[@type='sent']/tei:placeName"/>
        </p>
        <p><strong>Date:</strong>
            <xsl:value-of select="tei:correspAction[@type='sent']/tei:date/@when"/>
        </p>
    </xsl:template>
    
    <!-- Document container -->
    <xsl:template match="tei:div">
        <section>
            <xsl:attribute name="class">
                <xsl:text>tei-document </xsl:text>
                <xsl:value-of select="@type"/>
                <xsl:if test="@subtype">
                    <xsl:text> </xsl:text>
                    <xsl:value-of select="@subtype"/>
                </xsl:if>
            </xsl:attribute>
            <xsl:apply-templates/>
        </section>
    </xsl:template>
    
    <!-- Head -->
    <xsl:template match="tei:head">
        <h2><xsl:apply-templates/></h2>
    </xsl:template>
    
    <!-- Paragraph -->
    <xsl:template match="tei:p">
        <p><xsl:apply-templates/></p>
    </xsl:template>
    
    <!-- Page break / folio marker -->
    <xsl:template match="tei:pb | tei:seg[@type='folio']">
        <span class="folio-marker">
            <xsl:apply-templates/>
        </span>
    </xsl:template>
    
    <!-- Lists -->
    <xsl:template match="tei:list[@type='ordered']">
        <ol><xsl:apply-templates/></ol>
    </xsl:template>
    
    <xsl:template match="tei:item">
        <li>
            <xsl:if test="@facs">
                <xsl:attribute name="data-facs">
                    <xsl:value-of select="@facs"/>
                </xsl:attribute>
            </xsl:if>
            <xsl:apply-templates/>
        </li>
    </xsl:template>
    
    <!-- Figures -->
    <xsl:template match="tei:figure">
        <figure>
            <xsl:if test="@facs">
                <xsl:attribute name="data-facs">
                    <xsl:value-of select="@facs"/>
                </xsl:attribute>
            </xsl:if>
            
            <xsl:apply-templates select="tei:head"/>
            <xsl:apply-templates select="tei:graphic"/>
            <xsl:apply-templates select="tei:figDesc"/>
        </figure>
    </xsl:template>
    
    <xsl:template match="tei:graphic">
        <img>
            <xsl:attribute name="src">
                <xsl:value-of select="@url"/>
            </xsl:attribute>
        </img>
    </xsl:template>
    
    <xsl:template match="tei:figDesc">
        <figcaption>
            <xsl:apply-templates/>
        </figcaption>
    </xsl:template>
    
    <!-- Closer -->
    <xsl:template match="tei:closer">
        <section class="tei-closer">
            <xsl:apply-templates/>
        </section>
    </xsl:template>
    
    <xsl:template match="tei:signed">
        <p class="signature">
            <xsl:apply-templates/>
        </p>
    </xsl:template>
    
    <xsl:template match="tei:label">
        <p class="signature-label">
            <em><xsl:apply-templates/></em>
        </p>
    </xsl:template>
    
    <!-- Inline entities -->
    <xsl:template match="tei:persName | tei:placeName | tei:orgName | tei:date">
        <span>
            <xsl:attribute name="class">
                <xsl:value-of select="local-name()"/>
            </xsl:attribute>
            <xsl:if test="@ref">
                <xsl:attribute name="data-ref">
                    <xsl:value-of select="@ref"/>
                </xsl:attribute>
            </xsl:if>
            <xsl:apply-templates/>
        </span>
    </xsl:template>
    
    <!-- Choice: show expanded form -->
    <xsl:template match="tei:choice">
        <xsl:apply-templates select="tei:expan | tei:corr | node()"/>
    </xsl:template>
    
    <!-- Line breaks -->
    <xsl:template match="tei:lb">
        <br/>
    </xsl:template>
    
    <!-- Default -->
    <xsl:template match="*">
        <xsl:apply-templates/>
    </xsl:template>
    
</xsl:stylesheet>